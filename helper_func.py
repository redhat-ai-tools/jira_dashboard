#!/usr/bin/env python3
"""
Helper functions
"""

import os
import json
import re
import yaml
from datetime import datetime, timedelta, timezone
from crewai import Agent, Task


def load_agents_config():
    """Load agent configurations from YAML file"""
    with open('agents.yaml', 'r') as f:
        return yaml.safe_load(f)


def load_tasks_config():
    """Load task configurations from YAML file"""
    with open('tasks.yaml', 'r') as f:
        return yaml.safe_load(f)


def create_agent_from_config(agent_name, config, mcp_tools=None, llm=None):
    """Create an agent from YAML configuration"""
    tools = mcp_tools if config.get('requires_tools', False) else []
    
    return Agent(
        role=config['role'],
        goal=config['goal'],
        backstory=config['backstory'],
        tools=tools,
        llm=llm,
        verbose=config.get('verbose', True)
    )


def create_task_from_config(task_name, config, agents_dict, **template_vars):
    """Create a task from YAML configuration with optional template substitution"""
    # Handle template substitution
    description = config['description']
    expected_output = config['expected_output']
    
    # Substitute template variables if provided
    if template_vars:
        description = description.format(**template_vars)
        expected_output = expected_output.format(**template_vars)
    
    # Get agent name and resolve to actual agent
    agent_name = config['agent']
    if template_vars and '{' in agent_name and '}' in agent_name:
        agent_name = agent_name.format(**template_vars)
    
    agent = agents_dict[agent_name]
    
    # Create task
    task_kwargs = {
        'description': description,
        'agent': agent,
        'expected_output': expected_output
    }
    
    # Add output_file if specified
    if 'output_file' in config:
        output_file = config['output_file']
        # Apply template substitution to output_file if template variables are provided
        if template_vars and '{' in output_file and '}' in output_file:
            output_file = output_file.format(**template_vars)
        task_kwargs['output_file'] = output_file
    
    return Task(**task_kwargs)


def create_agents(mcp_tools, llm):
    """Create all agents from YAML configuration"""
    agents_config = load_agents_config()
    agents = {}
    
    for agent_name, config in agents_config['agents'].items():
        agents[agent_name] = create_agent_from_config(agent_name, config, mcp_tools, llm)
    
    return agents


def format_timestamp(timestamp):
    """Convert timestamp to readable format"""
    if not timestamp or timestamp == 'None' or timestamp == '':
        return "Not Set"
    
    try:
        # First check if it's already a formatted string (like "2025-07-29 08:38:53")
        if isinstance(timestamp, str):
            # Check if it's already in readable format (contains hyphen for date)
            if '-' in timestamp and len(timestamp) > 10:
                return timestamp
            
            # Handle JIRA timestamp format: "1753460716.477000000 1440" or just "1753460716.477000000"
            timestamp_parts = timestamp.strip().split()
            if timestamp_parts:
                timestamp_str = timestamp_parts[0]
                # Try to convert to float - this should be a UNIX timestamp
                try:
                    if '.' in timestamp_str:
                        timestamp_float = float(timestamp_str)
                    else:
                        timestamp_float = float(timestamp_str)
                    dt = datetime.fromtimestamp(timestamp_float)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    # If it can't be converted to float, it might be a different format
                    return timestamp
                    
        elif isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
            
        return "Unknown Format"
    except Exception as e:
        # Debug: print the actual timestamp value that caused the error
        print(f"   ⚠️  Debug: Failed to format timestamp '{timestamp}' (type: {type(timestamp)}): {e}")
        return f"Invalid ({type(timestamp).__name__})"


def is_timestamp_within_days(timestamp, days=14):
    """Check if timestamp is within the last n days"""
    if not timestamp:
        return False
    
    try:
        # Normalize to datetime
        dt = None
        if isinstance(timestamp, str):
            ts = timestamp.strip()
            # Try ISO 8601 first (e.g., 2025-08-07T14:16:52.866000+00:00 or 2025-08-07T14:16:52Z)
            if ('T' in ts and '-' in ts) or (('-' in ts) and (':' in ts)):
                try:
                    ts_iso = ts.replace('Z', '+00:00')
                    dt_parsed = datetime.fromisoformat(ts_iso)
                    # Convert aware datetimes to naive UTC for comparison consistency
                    if dt_parsed.tzinfo is not None:
                        dt = dt_parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    else:
                        dt = dt_parsed
                except Exception:
                    dt = None
            # If not ISO 8601, try numeric epoch optionally followed by offset (e.g., "1753460716.477000000 1440")
            if dt is None:
                timestamp_parts = ts.split()
                if timestamp_parts:
                    timestamp_str = timestamp_parts[0]
                    try:
                        timestamp_float = float(timestamp_str)
                        dt = datetime.fromtimestamp(timestamp_float)
                    except Exception:
                        return False
                else:
                    return False
        elif isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        else:
            return False
        
        # Check if within last n days
        cutoff_date = datetime.now() - timedelta(days=days)
        return dt >= cutoff_date
        
    except Exception as e:
        return False


def calculate_item_metrics(all_items, analysis_period_days=14, item_type="item"):
    """
    Calculate metrics for items (bugs, stories, tasks).
    
    Args:
        all_items: List of items from JIRA
        analysis_period_days: Number of days to look back for recent activity
        item_type: Type of items being analyzed ("bug", "story", "task", etc.)
    
    Returns:
        Dictionary with metrics and categorized item lists
    """
    def is_resolved(resolution_date):
        """Check if item is resolved"""
        return resolution_date and resolution_date != 'Unknown' and resolution_date != 'Invalid'
    
    # Initialize metrics based on item type
    if item_type.lower() == "bug":
        metrics = {
            'total_blocker_bugs': 0,
            'total_critical_bugs': 0,
            'total_blocker_bugs_resolved': 0,
            'total_critical_bugs_resolved': 0,
            'blocker_bugs_recent_activity': 0,
            'critical_bugs_recent_activity': 0,
            'blocker_bugs_created_recently': 0,
            'critical_bugs_created_recently': 0,
            'blocker_bugs_resolved_recently': 0,
            'critical_bugs_resolved_recently': 0
        }
    else:
        metrics = {
            'total_items': 0,
            'total_resolved_items': 0,
            'items_recent_activity': 0,
            'items_created_recently': 0,
            'items_resolved_recently': 0,
            'priority_breakdown': {}
        }
    
    recent_activity_items = []
    recently_created_items = []
    recently_resolved_items = []
    
    for item in all_items:
        priority = item.get('priority', 'Unknown')  # Use raw priority value
        created = item.get('created', '')
        updated = item.get('updated', '') 
        resolution_date = item.get('resolution_date', '')
        
        is_item_resolved = is_resolved(resolution_date)
        
        # Handle different item types
        if item_type.lower() == "bug":
            is_blocker = priority == '1'  # Priority 1 = Blocker
            is_critical = priority == '2'  # Priority 2 = Critical
            
            # Bug-specific metrics
            if is_blocker:
                metrics['total_blocker_bugs'] += 1
                if is_item_resolved:
                    metrics['total_blocker_bugs_resolved'] += 1
            elif is_critical:
                metrics['total_critical_bugs'] += 1
                if is_item_resolved:
                    metrics['total_critical_bugs_resolved'] += 1
        else:
            # General item metrics
            metrics['total_items'] += 1
            if is_item_resolved:
                metrics['total_resolved_items'] += 1
            
            # Track priority breakdown
            if priority in metrics['priority_breakdown']:
                metrics['priority_breakdown'][priority] += 1
            else:
                metrics['priority_breakdown'][priority] = 1
        
        # All items have recent activity (due to timeframe=14 in database query)
        recent_activity_items.append({
            'key': item.get('key', 'Unknown'),
            'summary': item.get('summary', 'No summary'),
            'priority': priority,  # Use raw priority value
            'status': item.get('status', 'Unknown'),
            'updated': format_timestamp(updated),
            'created': format_timestamp(created),
            'resolution_date': format_timestamp(resolution_date)
        })
        
        # Count items with recent activity for bug-specific metrics
        if item_type.lower() == "bug":
            is_blocker = priority == '1'
            is_critical = priority == '2'
            if is_blocker:
                metrics['blocker_bugs_recent_activity'] += 1
            elif is_critical:
                metrics['critical_bugs_recent_activity'] += 1
        else:
            metrics['items_recent_activity'] += 1
        
        # Check if ACTUALLY created recently (not just has recent activity)
        if is_timestamp_within_days(created, analysis_period_days):
            recently_created_items.append({
                'key': item.get('key', 'Unknown'),
                'summary': item.get('summary', 'No summary'),
                'priority': priority,
                'created': format_timestamp(created)
            })
            
            # Count recently created for specific metrics
            if item_type.lower() == "bug":
                if priority == '1':
                    metrics['blocker_bugs_created_recently'] += 1
                elif priority == '2':
                    metrics['critical_bugs_created_recently'] += 1
            else:
                metrics['items_created_recently'] += 1
        
        # Check if ACTUALLY resolved recently (not just has recent activity)
        if is_item_resolved and is_timestamp_within_days(resolution_date, analysis_period_days):
            recently_resolved_items.append({
                'key': item.get('key', 'Unknown'),
                'summary': item.get('summary', 'No summary'),
                'priority': priority,
                'resolution_date': format_timestamp(resolution_date)
            })
            
            # Count recently resolved for specific metrics
            if item_type.lower() == "bug":
                if priority == '1':
                    metrics['blocker_bugs_resolved_recently'] += 1
                elif priority == '2':
                    metrics['critical_bugs_resolved_recently'] += 1
            else:
                metrics['items_resolved_recently'] += 1
    
    return {
        'metrics': metrics,
        'recent_activity_items': recent_activity_items,
        'recently_created_items': recently_created_items,
        'recently_resolved_items': recently_resolved_items
    }


def extract_json_from_result(result_text):
    """Extract JSON data from CrewAI result - handles markdown code blocks and various formats"""
    if isinstance(result_text, dict):
        return result_text
    
    if hasattr(result_text, 'raw'):
        if isinstance(result_text.raw, dict):
            return result_text.raw
        elif isinstance(result_text.raw, str):
            try:
                return json.loads(result_text.raw)
            except:
                pass
    
    # Try parsing as string
    result_str = str(result_text).strip()
    
    # Handle markdown code blocks (```json ... ``` or ``` ... ```)
    if result_str.startswith('```'):
        lines = result_str.split('\n')
        # Find start line (skip ```json or ```)
        start_idx = 1 if lines[0].strip() in ['```json', '```'] else 0
        # Find end line (look for closing ```)
        end_idx = len(lines)
        for i in range(start_idx, len(lines)):
            if lines[i].strip() == '```':
                end_idx = i
                break
        # Extract content between code blocks
        json_content = '\n'.join(lines[start_idx:end_idx])
        try:
            return json.loads(json_content)
        except:
            # If that fails, fall through to other methods
            result_str = json_content.strip()
    
    try:
        return json.loads(result_str)
    except:
        # Try extracting JSON with proper brace matching (handles strings and escapes)
        if result_str.startswith('{'):
            brace_count = 0
            in_string = False
            escape_next = False
            end_idx = -1
            
            for i, char in enumerate(result_str):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                if char == '"' and not in_string:
                    in_string = True
                    continue
                if char == '"' and in_string:
                    in_string = False
                    continue
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
            
            if end_idx != -1:
                json_str = result_str[:end_idx]
                try:
                    return json.loads(json_str)
                except:
                    pass
    
    return None


def parse_epic_summaries(filename):
    """Parse the recently_updated_epics_summary.txt file and extract epic-level summaries"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        epic_summaries = []
        
        # Split content by epic sections (look for "1. EPIC:", "2. EPIC:", etc.)
        epic_sections = re.split(r'\n\d+\. EPIC: ', content)
        
        for i, section in enumerate(epic_sections[1:], 1):  # Skip first empty split
            lines = section.split('\n')
            if not lines:
                continue
                
            # Extract epic key from first line
            epic_key = lines[0].strip()
            
            # Find the EPIC-LEVEL SUMMARY section
            epic_level_summary = ""
            in_epic_summary = False
            
            for line in lines:
                if "EPIC-LEVEL SUMMARY" in line:
                    in_epic_summary = True
                    continue
                elif line.startswith("=" * 80) and in_epic_summary:
                    break
                elif in_epic_summary and line.strip():
                    if not line.startswith("-" * 40):  # Skip separator lines
                        epic_level_summary += line + "\n"
            
            if epic_level_summary.strip():
                epic_summaries.append({
                    'epic_key': epic_key,
                    'summary': epic_level_summary.strip()
                })
        
        print(f"✅ Parsed {len(epic_summaries)} epic summaries from {filename}")
        return epic_summaries
        
    except FileNotFoundError:
        print(f"❌ File {filename} not found. Please run full_epic_activity_analysis.py first.")
        return []
    except Exception as e:
        print(f"❌ Error parsing {filename}: {str(e)}")
        return []


def post_process_summary_timestamps(text):
    """Find and format any raw timestamps in summary text"""
    import re
    
    # Pattern to match timestamps like "1752850611.021000000 1440" or just "1752850611.021000000"
    timestamp_pattern = r'\b(1\d{9}(?:\.\d+)?)(?: \d+)?\b'
    
    def replace_timestamp(match):
        timestamp_str = match.group(1)
        try:
            timestamp_float = float(timestamp_str)
            dt = datetime.fromtimestamp(timestamp_float)
            formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            return formatted_date
        except:
            return match.group(0)  # Return original if conversion fails
    
    return re.sub(timestamp_pattern, replace_timestamp, text)



def filter_project_summary(project_summary_data, project):
    """Filter project summary data to only include specified project"""
    try:
        if isinstance(project_summary_data, str):
            import json
            project_summary_data = json.loads(project_summary_data)
        
        if not isinstance(project_summary_data, dict):
            return {"error": "Invalid project summary data format"}
        
        if "error" in project_summary_data:
            return project_summary_data
        
        projects = project_summary_data.get("projects", {})
        
        # Look for specified project (case-insensitive)
        target_project = None
        for project_name, project_data in projects.items():
            if project_name.upper() == project.upper():
                target_project = project_data
                break
        
        if target_project is None:
            return {
                "error": f"{project} project not found in summary",
                "available_projects": list(projects.keys()),
                "total_projects_found": len(projects)
            }
        
        # Return filtered summary with only specified project data
        return {
            "project_name": project,
            "total_issues": target_project.get("total_issues", 0),
            "statuses": target_project.get("statuses", {}),
            "priorities": target_project.get("priorities", {}),
            "summary": {
                f"total_{project.lower()}_issues": target_project.get("total_issues", 0),
                "status_breakdown": target_project.get("statuses", {}),
                "priority_breakdown": target_project.get("priorities", {})
            }
        }
        
    except Exception as e:
        return {"error": f"Error filtering {project} project summary: {str(e)}"}


class BugCalculator:
    """Universal bug calculation logic for any priority level"""
    
    def __init__(self, priority_ids, priority_name="Priority"):
        """
        Initialize calculator for specific priority levels
        
        Args:
            priority_ids: List of priority IDs to track (e.g., ["2"] for Critical, ["1"] for Blocker)
            priority_name: Human-readable name for the priority (e.g., "Critical", "Blocker")
        """
        self.priority_ids = priority_ids
        self.priority_name = priority_name
        self.bug_type_ids = ["1"]  # Bug type only
    
    def is_target_priority(self, priority):
        """Check if priority ID matches our target priority"""
        if not priority:
            return False
        return str(priority).strip() in self.priority_ids
    
    def is_bug_type(self, issue_type):
        """Check if issue type ID is a bug"""
        if not issue_type:
            return False
        return str(issue_type).strip() in self.bug_type_ids
    
    def is_resolved(self, resolution_date):
        """Check if issue is resolved using resolution_date field"""
        return resolution_date is not None and str(resolution_date).strip() != "" and str(resolution_date).strip().lower() != "null"
    
    def is_within_last_month(self, timestamp):
        """Check if timestamp is within the last 30 days"""
        if not timestamp:
            return False
        
        try:
            # Handle JIRA timestamp format: "1753460716.477000000 1440"
            if isinstance(timestamp, str):
                timestamp_parts = timestamp.strip().split()
                if timestamp_parts:
                    timestamp_str = timestamp_parts[0]
                    if '.' in timestamp_str:
                        timestamp_float = float(timestamp_str)
                    else:
                        timestamp_float = float(timestamp_str)
                    dt = datetime.fromtimestamp(timestamp_float)
                else:
                    return False
            elif isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                return False
            
            # Check if within last 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            return dt >= cutoff_date
            
        except Exception as e:
            return False

    def calculate_bug_metrics(self, issues):
        """Calculate the 3 key bug metrics for the configured priority"""
        priority_lower = self.priority_name.lower()
        metrics = {
            f'total_{priority_lower}_bugs': 0,
            f'total_{priority_lower}_bugs_resolved': 0,
            f'{priority_lower}_bugs_resolved_last_month': 0
        }
        
        bugs_fixed = []
        
        for issue in issues:
            issue_type = issue.get('issue_type', '')
            priority = issue.get('priority', '')
            resolution_date = issue.get('resolution_date', '')
            
            # Check if it's a target priority bug
            is_bug = self.is_bug_type(issue_type)
            is_target_priority = self.is_target_priority(priority) 
            is_resolved = self.is_resolved(resolution_date)
            
            if is_bug and is_target_priority:
                # 1. Total bugs of this priority
                metrics[f'total_{priority_lower}_bugs'] += 1
                
                if is_resolved:
                    # 2. Total bugs resolved (ever)
                    metrics[f'total_{priority_lower}_bugs_resolved'] += 1
                    
                    # 3. Bugs resolved in last month
                    if self.is_within_last_month(resolution_date):
                        metrics[f'{priority_lower}_bugs_resolved_last_month'] += 1
                        bugs_fixed.append({
                            'key': issue.get('key', 'N/A'),
                            'summary': issue.get('summary', 'N/A')[:100],
                            'resolution_date': resolution_date
                        })
        
        return metrics, bugs_fixed

    # Legacy method names for backward compatibility with existing code
    def calculate_critical_bug_metrics(self, issues):
        """Legacy method - use calculate_bug_metrics instead"""
        return self.calculate_bug_metrics(issues)
        
    def calculate_blocker_bug_metrics(self, issues):
        """Legacy method - use calculate_bug_metrics instead"""
        return self.calculate_bug_metrics(issues)

    def extract_json_from_result(self, result_text):
        """Extract JSON data from CrewAI result"""
        if isinstance(result_text, dict):
            return result_text
        
        if hasattr(result_text, 'raw'):
            if isinstance(result_text.raw, dict):
                return result_text.raw
            elif isinstance(result_text.raw, str):
                try:
                    return json.loads(result_text.raw)
                except:
                    pass
        
        # Try parsing as string
        result_str = str(result_text).strip()
        try:
            return json.loads(result_str)
        except:
            # Try extracting JSON with brace matching
            if result_str.startswith('{'):
                brace_count = 0
                in_string = False
                escape_next = False
                end_idx = -1
                
                for i, char in enumerate(result_str):
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\' and in_string:
                        escape_next = True
                        continue
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                
                if end_idx != -1:
                    json_str = result_str[:end_idx]
                    try:
                        return json.loads(json_str)
                    except:
                        pass
        
        return None


def calculate_total_issues(all_issues):
    """
    Simple function to calculate total number of issues.
    
    Args:
        all_issues: List of issues from JIRA
    
    Returns:
        Integer count of total issues
    """
    return len(all_issues) if all_issues else 0


def map_priority(priority_id):
    """
    Map priority ID to human-readable label.
    
    Args:
        priority_id: Priority ID from JIRA
    
    Returns:
        String with human-readable priority label
    """
    priority_mapping = {
        '10200': 'Normal',
        '3': 'Major',
        '1': 'Blocker',
        '2': 'Critical'
    }
    return priority_mapping.get(str(priority_id), str(priority_id))


def map_status(status_id):
    """
    Map status ID to human-readable label.
    
    Args:
        status_id: Status ID from JIRA
    
    Returns:
        String with human-readable status label
    """
    status_mapping = {
        '6': 'Resolved/Closed',
        '10018': 'In Progress',
        '10016': 'New',
        '12422': 'Review'
    }
    return status_mapping.get(str(status_id), str(status_id))


def map_issue_type(issue_type_id):
    """
    Map issue type ID to human-readable label.
    
    Args:
        issue_type_id: Issue type ID from JIRA
    
    Returns:
        String with human-readable issue type label
    """
    issue_type_mapping = {
        '10700': 'Feature',
        '1': 'Bug', 
        '16': 'Epic',
        '17': 'Story',
        '3': 'Task'
    }
    return issue_type_mapping.get(str(issue_type_id), str(issue_type_id))


def convert_markdown_to_html(text):
    """
    Convert common markdown elements to HTML.
    
    Args:
        text: Markdown text to convert
    
    Returns:
        HTML formatted text
    """
    
    # Convert text to string if it isn't already
    html_text = str(text)
    
    # Remove bold formatting first (** or __)
    html_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', html_text)
    html_text = re.sub(r'__([^_]+)__', r'\1', html_text)
    
    # Convert newlines to <br>
    html_text = html_text.replace('\n', '<br>')
    
    # Convert markdown headings to HTML headings
    html_text = re.sub(r'<br>###\s*([^<]+?)(?=<br>|$)', r'<br><h3>\1</h3><br>', html_text)
    html_text = re.sub(r'<br>##\s*([^<]+?)(?=<br>|$)', r'<br><h2>\1</h2><br>', html_text)
    html_text = re.sub(r'<br>#\s*([^<]+?)(?=<br>|$)', r'<br><h1>\1</h1><br>', html_text)
    
    # Handle headings at the beginning of text
    html_text = re.sub(r'^###\s*([^<]+?)(?=<br>|$)', r'<h3>\1</h3><br>', html_text)
    html_text = re.sub(r'^##\s*([^<]+?)(?=<br>|$)', r'<h2>\1</h2><br>', html_text)
    html_text = re.sub(r'^#\s*([^<]+?)(?=<br>|$)', r'<h1>\1</h1><br>', html_text)
    
    # Convert simple bullet points to list items
    def convert_bullet(match):
        content = match.group(1).strip()
        # Skip placeholder items
        if content in ['--', '---', '—', '–', '...', '.', '-'] or len(content) <= 2:
            return ''
        return f'<br><li>{content}</li>'
    
    html_text = re.sub(r'<br>[*\-•]\s*([^<]+?)(?=<br>|$)', convert_bullet, html_text)
    
    # Convert numbered lists
    html_text = re.sub(r'<br>(\d+)\.\s*([^<]+?)(?=<br>|$)', r'<br><li>\2</li>', html_text)
    
    # Wrap consecutive <li> items in <ul> tags
    html_text = re.sub(r'(<br><li>[^<]*</li>)(<br><li>[^<]*</li>)+', 
                      lambda m: '<ul>' + m.group(0).replace('<br><li>', '<li>') + '</ul>', html_text)
    
    # Handle single <li> items
    html_text = re.sub(r'<br><li>([^<]*)</li>(?!</ul>)', r'<ul><li>\1</li></ul>', html_text)
    
    # Clean up extra <br> tags
    html_text = re.sub(r'<br>(<[h|u])', r'\1', html_text)
    html_text = re.sub(r'(<br>){3,}', r'<br><br>', html_text)
    
    return html_text


def filter_test_issues(issues):
    """
    Filter out test issues from the list.
    
    Args:
        issues: List of issue dictionaries
    
    Returns:
        List of issues with test issues removed
    """
    filtered_issues = []
    removed_count = 0
    
    for issue in issues:
        summary = issue.get('summary', '').lower()
        if summary.strip() == 'test':
            removed_count += 1
            continue
        filtered_issues.append(issue)
    
    if removed_count > 0:
        print(f"   🧹 Filtered out {removed_count} test issues")
    
    return filtered_issues


def add_jira_links_to_html(html_content, project_key, jira_base_url=None):
    """
    Add clickable links to JIRA issue keys in HTML content that don't already have links.
    
    Args:
        html_content: The HTML content as a string
        project_key: The JIRA project key
        jira_base_url: Base URL for JIRA links
    
    Returns:
        String with HTML content where unlinked JIRA issues are now linked
        
    Note:
        - Requires JIRA_BASE_URL environment variable to be set for linking to work
        - If JIRA_BASE_URL is not set or empty, linking will be disabled
        - Only processes issue keys that aren't already in <a> tags
    """
    
    # Use provided URL, or fall back to environment variable
    if jira_base_url is None:
        jira_base_url = os.getenv("JIRA_BASE_URL")
    
    # If no valid URL is provided, return original content without linking
    if not jira_base_url or jira_base_url.strip() == "":
        return html_content
    
    # Ensure URL ends with a slash for proper concatenation
    if not jira_base_url.endswith('/'):
        jira_base_url += '/'
    
    # Pattern to match JIRA issue keys (PROJECT-NUMBER)
    pattern = rf'\b({project_key}-\d+)\b'
    
    def replace_with_link(match):
        issue_key = match.group(1)
        full_match = match.group(0)
        
        # Check if this issue key is already part of a link
        # Look for href= before the match and </a> after the match
        start_pos = match.start()
        end_pos = match.end()
        
        # Check if we're inside an href attribute (look backwards for href=")
        before_text = html_content[max(0, start_pos-200):start_pos]
        if 'href="' in before_text:
            # Find the last href=" in the before text
            last_href_pos = before_text.rfind('href="')
            # Check if there's a closing quote between href=" and our match
            text_after_href = before_text[last_href_pos+6:]  # +6 for 'href="'
            if '"' not in text_after_href:
                # We're inside an href attribute, don't link
                return full_match
        
        # Check if we're inside an <a> tag (look backwards for <a and forwards for </a>)
        before_text_short = html_content[max(0, start_pos-100):start_pos]
        after_text_short = html_content[end_pos:min(len(html_content), end_pos+100)]
        
        if '<a ' in before_text_short and '</a>' in after_text_short:
            # Check if there's a closing </a> before our position
            last_a_open = before_text_short.rfind('<a ')
            last_a_close = before_text_short.rfind('</a>')
            if last_a_open > last_a_close:
                # We're inside an <a> tag, don't link
                return full_match
        
        # Create the link
        return f'<a href="{jira_base_url}{issue_key}" target="_blank">{issue_key}</a>'
    
    # Replace unlinked JIRA issue keys with links
    linked_html = re.sub(pattern, replace_with_link, html_content)
    
    return linked_html


def generate_html_report(project, analysis_period_days, components, total_issues, issues_sample, executive_summary, jira_base_url=None):
    """Generate HTML report with executive summary and issue details"""
    import os
    from datetime import datetime
    
    # Use provided URL or get from environment
    if jira_base_url is None:
        jira_base_url = os.getenv("JIRA_BASE_URL", "")
    
    # Format components display
    components_display = f"<strong>Components:</strong> {components}" if components else "<strong>Components:</strong> All"
    
    # Process executive summary to convert markdown to HTML
    executive_summary_html = convert_markdown_to_html(executive_summary)
    
    # Generate issues table
    issues_table_rows = ""
    for issue in issues_sample:
        issue_key = issue.get('key', 'Unknown')
        issue_link = f"{jira_base_url}/{issue_key}" if jira_base_url else f"#{issue_key}"
        component_list = ', '.join(issue.get('component', [])) if issue.get('component') else 'None'
        
        # Map IDs to human-readable labels
        issue_type_label = map_issue_type(issue.get('issue_type', 'Unknown'))
        priority_label = map_priority(issue.get('priority', 'Unknown'))
        status_label = map_status(issue.get('status', 'Unknown'))
        
        description_preview = issue.get('description', 'No description')
        
        issues_table_rows += f"""
        <tr>
            <td><a href="{issue_link}" target="_blank">{issue_key}</a></td>
            <td title="{description_preview}">{issue.get('summary', 'No summary')}</td>
            <td>{issue_type_label}</td>
            <td>{priority_label}</td>
            <td>{status_label}</td>
            <td>{component_list}</td>
        </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project} Executive Issues Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin: -30px -30px 30px -30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .subtitle {{
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.2em;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.9em;
        }}
        .executive-summary {{
            background: linear-gradient(135deg, #fff9e6 0%, #fdfbf0 100%);
            border: 1px solid #ffd700;
            border-radius: 12px;
            padding: 0;
            margin: 30px 0;
            box-shadow: 0 4px 15px rgba(184, 134, 11, 0.1);
            overflow: hidden;
        }}
        .executive-summary .summary-header {{
            background: linear-gradient(135deg, #8b6914 0%, #b8860b 100%);
            color: white;
            padding: 20px 25px;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}
        .executive-summary .summary-header h2 {{
            margin: 0;
            font-size: 1.6em;
            font-weight: 700;
            color: #ffffff;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.4);
        }}
        .executive-summary .summary-content {{
            padding: 30px;
            max-width: none;
        }}
        .executive-summary .content-section {{
            margin: 30px 0;
            padding-bottom: 20px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .executive-summary .content-section:last-child {{
            border-bottom: none;
        }}
        .executive-summary h2 {{
            color: #b8860b;
            margin-top: 0;
        }}
        .executive-summary h1 {{
            color: #b8860b;
            margin: 0 0 30px 0;
            font-size: 1.7em;
            border-bottom: 3px solid #ffd700;
            padding-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 600;
        }}
        .executive-summary h1:before {{
            content: "📊";
            font-size: 1.3em;
        }}
        .executive-summary h3 {{
            color: #8b7355;
            margin: 40px 0 25px 0;
            font-size: 1.4em;
            font-weight: 600;
            padding: 20px 25px;
            background: linear-gradient(135deg, #f8f4e6 0%, #faf7ed 100%);
            border-left: 5px solid #daa520;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            box-shadow: 0 3px 10px rgba(184, 134, 11, 0.1);
        }}
        .executive-summary h3:before {{
            content: "🔍";
            font-size: 1.2em;
        }}
        .executive-summary ul {{
            margin: 25px 0;
            padding: 0;
            list-style: none;
        }}
        .executive-summary li {{
            margin: 12px 0;
            padding: 20px 25px;
            background: white;
            border-radius: 12px;
            border-left: 5px solid #ffd700;
            line-height: 1.8;
            box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08);
            position: relative;
            transition: all 0.3s ease;
            font-size: 1.05em;
        }}
        .executive-summary li:hover {{
            transform: translateX(8px);
            box-shadow: 0 6px 20px rgba(184, 134, 11, 0.2);
        }}
        .executive-summary li:before {{
            content: "●";
            color: #b8860b;
            font-weight: bold;
            position: absolute;
            left: 8px;
            top: 30px;
            font-size: 12px;
        }}
        .executive-summary .action-item {{
            margin: 8px 0 8px 20px;
            padding: 12px 15px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #667eea;
            line-height: 1.6;
            font-size: 0.95em;
            color: #555;
        }}
        .executive-summary p {{
            margin: 20px 0;
            line-height: 1.8;
            color: #444;
            font-size: 1.05em;
        }}
        .executive-summary a {{
            color: #667eea;
            font-weight: 500;
            text-decoration: none;
            padding: 2px 4px;
            border-radius: 3px;
            background: rgba(102, 126, 234, 0.1);
            transition: all 0.2s ease;
        }}
        .executive-summary a:hover {{
            background: rgba(102, 126, 234, 0.2);
            text-decoration: none;
        }}
        .executive-summary .highlight-box {{
            background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%);
            border: 1px solid #0066cc;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #0066cc;
        }}
        .executive-summary .warning-box {{
            background: linear-gradient(135deg, #fff2e6 0%, #fffaf5 100%);
            border: 1px solid #ff6600;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #ff6600;
        }}
        .executive-summary .success-box {{
            background: linear-gradient(135deg, #e6ffe6 0%, #f5fff5 100%);
            border: 1px solid #00cc66;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #00cc66;
        }}
        .table-container {{
            overflow-x: auto;
            margin: 30px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #667eea;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #666;
            text-align: center;
        }}
        a {{
            color: #667eea;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .section {{
            margin: 30px 0;
        }}
        .section h2 {{
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {project} Executive Issues Report</h1>
            <div class="subtitle">Strategic Analysis of Recently Created Issues</div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_issues}</div>
                <div class="stat-label">Total Issues Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analysis_period_days}</div>
                <div class="stat-label">Days Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(issues_sample)}</div>
                <div class="stat-label">Issues in Table</div>
            </div>
        </div>

        <div class="section">
            <h2>📋 Analysis Parameters</h2>
            <p><strong>Project:</strong> {project}</p>
            <p><strong>Time Period:</strong> Last {analysis_period_days} days</p>
            <p>{components_display}</p>
            <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="executive-summary">
            <div class="summary-header">
                <h2>🎯 Executive Summary</h2>
            </div>
            <div class="summary-content">
                {executive_summary_html}
            </div>
        </div>

        <div class="section">
            <h2>📊 Recently Created Issues</h2>
            <p>Showing all {len(issues_sample)} issues created in the last {analysis_period_days} days:</p>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Issue Key</th>
                            <th>Summary</th>
                            <th>Type</th>
                            <th>Priority</th>
                            <th>Status</th>
                            <th>Components</th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues_table_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer">
            <p>Report generated by JIRA Analysis System | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Add links to JIRA issue keys that don't already have links
    html_content = add_jira_links_to_html(html_content, project, jira_base_url)
    
    return html_content


def extract_html_from_result(result_text):
    """Extract HTML content from CrewAI result"""
    # Convert result to string if it's not already
    result_str = str(result_text)
    
    # Look for HTML content between ```html and ``` or just starting with <!DOCTYPE
    html_patterns = [
        r'```html\s*(<!DOCTYPE.*?)```',
        r'(<!DOCTYPE html.*?)(?=```|\Z)',
        r'(<!DOCTYPE.*)',
    ]
    
    for pattern in html_patterns:
        match = re.search(pattern, result_str, re.DOTALL | re.IGNORECASE)
        if match:
            html_content = match.group(1).strip()
            # Clean up any remaining markdown artifacts
            html_content = re.sub(r'^```html\s*', '', html_content)
            html_content = re.sub(r'\s*```$', '', html_content)
            return html_content
    
    # If no HTML found, return the raw result
    return result_str 