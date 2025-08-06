#!/usr/bin/env python3
"""
Helper functions for the Consolidated KONFLUX Summary Generator
"""

import os
import json
import re
import yaml
from datetime import datetime, timedelta
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
        task_kwargs['output_file'] = config['output_file']
    
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


# New helper functions from crewai_konflux_dashboard.py

def filter_konflux_project_summary(project_summary_data):
    """Filter project summary data to only include KONFLUX project"""
    try:
        if isinstance(project_summary_data, str):
            import json
            project_summary_data = json.loads(project_summary_data)
        
        if not isinstance(project_summary_data, dict):
            return {"error": "Invalid project summary data format"}
        
        if "error" in project_summary_data:
            return project_summary_data
        
        projects = project_summary_data.get("projects", {})
        
        # Look for KONFLUX project (case-insensitive)
        konflux_project = None
        for project_name, project_data in projects.items():
            if project_name.upper() == "KONFLUX":
                konflux_project = project_data
                break
        
        if konflux_project is None:
            return {
                "error": "KONFLUX project not found in summary",
                "available_projects": list(projects.keys()),
                "total_projects_found": len(projects)
            }
        
        # Return filtered summary with only KONFLUX data
        return {
            "project_name": "KONFLUX",
            "total_issues": konflux_project.get("total_issues", 0),
            "statuses": konflux_project.get("statuses", {}),
            "priorities": konflux_project.get("priorities", {}),
            "summary": {
                "total_konflux_issues": konflux_project.get("total_issues", 0),
                "status_breakdown": konflux_project.get("statuses", {}),
                "priority_breakdown": konflux_project.get("priorities", {})
            }
        }
        
    except Exception as e:
        return {"error": f"Error filtering KONFLUX project summary: {str(e)}"}


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