#!/usr/bin/env python3
"""
Consolidated KONFLUX Summary Generator
Reads the recently_updated_epics_summary.txt file and creates a consolidated summary containing:
1. Epic-level summaries only (extracted from existing file)
2. Critical/blocker bugs analysis from KONFLUX project (last 14 days)
"""

import os
import json
import re
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter

# Configuration
ANALYSIS_PERIOD_DAYS = 14  # Period for bug analysis

# Configure Gemini LLM
gemini_api_key = os.getenv("GEMINI_API_KEY")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=gemini_api_key,
    temperature=0.1,
)

# MCP Server configuration
server_params = {
    "url": "https://jira-mcp-snowflake.mcp-playground-poc.devshift.net/sse",
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": snowflake_token
    }
}

def create_bug_analyzer(mcp_tools):
    """Create specialized agent for analyzing critical bugs and blockers"""
    return Agent(
        role="Critical Bug and Blocker Analyzer",
        goal="Analyze critical bugs and blocker issues to extract key insights about problems, resolution efforts, and current status",
        backstory="""You are an expert at analyzing JIRA bug reports and blocker issues.
        You examine bug descriptions, comments, and activity to understand:
        - What the problem/issue is and its impact
        - What investigation and resolution efforts have been made
        - Current status and any challenges in resolution
        - Technical details and root causes when available
        
        You create concise but comprehensive summaries that help stakeholders understand
        the bug's significance, progress toward resolution, and any blockers preventing fixes.

        CRITICAL: You NEVER mention specific dates or timestamps in your summaries. All necessary
        dates are pre-formatted in the data provided to you. Focus on technical content, problem
        analysis, and resolution efforts, not date details.""",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_story_task_analyzer(mcp_tools):
    """Create specialized agent for analyzing stories and tasks"""
    return Agent(
        role="Story and Task Progress Analyzer",
        goal="Analyze JIRA stories and tasks to extract key insights about progress, achievements, implementation details, and current status",
        backstory="""You are an expert at analyzing JIRA stories and tasks to understand project progress and implementation details.
        You examine story/task descriptions, comments, and activity to understand:
        - What functionality or work was implemented or is being worked on
        - What progress has been made and what challenges were encountered
        - Technical implementation details and decisions made
        - Current status and any blockers preventing completion
        - Business value and impact of the work

        You create concise but comprehensive summaries that help stakeholders understand
        what work has been accomplished, what's in progress, and what challenges exist.

        CRITICAL: You NEVER mention specific dates or timestamps in your summaries. All necessary
        dates are pre-formatted in the data provided to you. Focus on technical content, business
        value, implementation progress, and challenges, not date details.""",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_bug_fetcher(mcp_tools):
    """Create agent for fetching bug data"""
    return Agent(
        role="JIRA Bug Data Fetcher",
        goal="Fetch critical and blocker bugs from KONFLUX project efficiently",
        backstory="You systematically retrieve bug data from JIRA using the available tools.",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_blocker_bug_fetcher(mcp_tools):
    """Create specialized agent for fetching BLOCKER bugs (priority=1)"""
    return Agent(
        role="JIRA Blocker Bug Fetcher",
        goal="Fetch BLOCKER bugs (priority=1) from KONFLUX project",
        backstory="You are specialized in retrieving BLOCKER priority bugs (priority=1) from JIRA. You ONLY fetch bugs with priority=1.",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_critical_bug_fetcher(mcp_tools):
    """Create specialized agent for fetching CRITICAL bugs (priority=2)"""
    return Agent(
        role="JIRA Critical Bug Fetcher", 
        goal="Fetch CRITICAL bugs (priority=2) from KONFLUX project",
        backstory="You are specialized in retrieving CRITICAL priority bugs (priority=2) from JIRA. You ONLY fetch bugs with priority=2.",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_story_fetcher(mcp_tools):
    """Create agent for fetching story data"""
    return Agent(
        role="JIRA Story Data Fetcher",
        goal="Fetch story issues from KONFLUX project efficiently",
        backstory="You systematically retrieve story data from JIRA using the available tools.",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_task_fetcher(mcp_tools):
    """Create agent for fetching task data"""
    return Agent(
        role="JIRA Task Data Fetcher",
        goal="Fetch task issues from KONFLUX project efficiently",
        backstory="You systematically retrieve task data from JIRA using the available tools.",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_epic_progress_analyzer():
    """Create specialized agent for analyzing epic progress and identifying significant changes"""
    return Agent(
        role="Epic Progress and Achievement Analyzer",
        goal="Analyze epic summaries to identify those with significant changes, extract key achievements, and determine next steps",
        backstory="""You are an expert at analyzing project progress and identifying meaningful developments.
        You examine epic summaries to understand:
        - Which epics show significant progress or changes
        - What major achievements have been accomplished
        - What challenges and blockers are present
        - What the next steps and priorities should be
        
        You focus on business impact, technical progress, and strategic direction.
        You can distinguish between routine updates and truly significant developments
        that would be important for stakeholders to know about.
        
        CRITICAL: You provide clear, actionable insights and avoid repeating 
        information that doesn't add value. Focus on progress that moves the 
        needle forward for the project.""",
        tools=[],  # No tools needed - just text analysis
        llm=llm,
        verbose=True
    )



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
    """Extract JSON data from CrewAI result - using proven logic from crewai_konflux_dashboard.py"""
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

def main():
    """Main function to create consolidated summary"""
    print("🎯 KONFLUX Consolidated Summary Generator")
    print("="*80)
    print("📋 This will create separate analysis files:")
    print("   1. Epic progress analysis (filtered for significant changes)")
    print(f"   2. Critical/blocker bugs analysis from KONFLUX project (last {ANALYSIS_PERIOD_DAYS} days)")
    print(f"   3. Stories and tasks analysis from KONFLUX project (last {ANALYSIS_PERIOD_DAYS} days)")
    print("\n📄 Output files generated:")
    print("   • konflux_consolidated_summary.txt - Epic progress summary only")
    print("   • epic_summaries_only.txt - Complete epic summaries for reference")
    print("   • epic_progress_analysis.txt - Standalone epic progress analysis")
    print("   • konflux_bugs_analysis.txt - Complete bugs analysis")
    print("   • konflux_stories_tasks_analysis.txt - Stories and tasks analysis")
    print("="*80)
    
    if not gemini_api_key:
        print("⚠️  Warning: GEMINI_API_KEY environment variable not set")
        return
    
    # Step 1: Parse existing epic summaries
    print("\n📖 Step 1: Reading existing epic summaries...")
    epic_summaries = parse_epic_summaries('recently_updated_epics_summary.txt')
    
    if not epic_summaries:
        print("❌ No epic summaries found. Cannot proceed.")
        return
    
    # Save epic summaries to separate file for analysis
    print("💾 Saving epic summaries to separate file...")
    epic_summaries_filename = 'epic_summaries_only.txt'
    
    with open(epic_summaries_filename, 'w', encoding='utf-8') as f:
        f.write("KONFLUX EPIC SUMMARIES FOR ANALYSIS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Epics: {len(epic_summaries)}\n")
        f.write("=" * 80 + "\n\n")
        
        for i, epic in enumerate(epic_summaries, 1):
            f.write(f"{i}. EPIC: {epic['epic_key']}\n")
            f.write("-" * 60 + "\n")
            f.write(epic['summary'])
            f.write("\n\n" + "=" * 60 + "\n\n")
    
    print(f"✅ Epic summaries saved to: {epic_summaries_filename}")
    
    # Step 2: Fetch and analyze critical/blocker bugs
    print(f"\n🐛 Step 2: Analyzing critical/blocker bugs from KONFLUX (last {ANALYSIS_PERIOD_DAYS} days)...")
    
    try:
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create specialized agents for different bug types
            blocker_bug_fetcher = create_blocker_bug_fetcher(mcp_tools)
            critical_bug_fetcher = create_critical_bug_fetcher(mcp_tools)
            bug_analyzer = create_bug_analyzer(mcp_tools)
            story_fetcher = create_story_fetcher(mcp_tools)
            task_fetcher = create_task_fetcher(mcp_tools)
            
            # Fetch critical bugs (priority 1 - Blocker)
            print("   🔍 Fetching blocker bugs (priority=1)...")
            blocker_task = Task(
                description="""
                TASK: Use list_jira_issues to get all BLOCKER bugs from KONFLUX project with recent activity.
                
                EXACT PARAMETERS TO USE:
                - project='KONFLUX'
                - issue_type='1'
                - priority='1'
                - timeframe=14
                - limit=100
                
                CRITICAL INSTRUCTIONS:
                1. Call list_jira_issues with the exact parameters above
                2. The timeframe=14 parameter gets bugs created/updated/resolved in last 14 days
                3. Return ONLY the raw JSON output from the tool
                4. DO NOT add any explanations, thoughts, or additional text
                5. DO NOT add "Action:" or "Thought:" or any other text
                6. The response must be ONLY the JSON data returned by the MCP tool
                """,
                agent=blocker_bug_fetcher,
                expected_output="Raw JSON data from list_jira_issues tool with NO additional text - must be parseable as JSON",
                output_file="blocker_bugs.json"
            )
            
            # Fetch critical bugs (priority 2 - Critical)
            print("   🔍 Fetching critical bugs (priority=2)...")
            critical_task = Task(
                description="""
                TASK: Use list_jira_issues to get all CRITICAL bugs from KONFLUX project.
                
                EXACT PARAMETERS TO USE:
                - project='KONFLUX'
                - issue_type='1'
                - priority='2'
                - timeframe=14
                - limit=100
                
                CRITICAL INSTRUCTIONS:
                1. Call list_jira_issues with the exact parameters above
                2. Return ONLY the raw JSON output from the tool
                3. DO NOT add any explanations, thoughts, or additional text
                4. DO NOT add "Action:" or "Thought:" or any other text
                5. The response must be ONLY the JSON data returned by the MCP tool
                """,
                agent=critical_bug_fetcher,
                expected_output="Raw JSON data from list_jira_issues tool with NO additional text - must be parseable as JSON",
                output_file="critical_bugs.json"
            )
            
            # Execute bug fetching
            bug_crew = Crew(
                agents=[blocker_bug_fetcher, critical_bug_fetcher],
                tasks=[blocker_task, critical_task],
                verbose=True
            )
            
            bug_result = bug_crew.kickoff()
            
            # Process fetched bugs using task outputs (like full_epic_activity_analysis.py)
            all_bugs = []
            
            # Read bugs from the JSON files created by the agents and extract clean JSON
            try:
                # Process blocker bugs from JSON file
                try:
                    with open('blocker_bugs.json', 'r') as f:
                        file_content = f.read()
                    blocker_data = extract_json_from_result(file_content)
                    if blocker_data and 'issues' in blocker_data:
                        print(f"   📊 Found {len(blocker_data['issues'])} blocker bugs from query")
                        all_bugs.extend(blocker_data['issues'])
                    else:
                        print(f"   ⚠️  No blocker bugs data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read blocker_bugs.json: {e}")
                
                # Process critical bugs from JSON file
                try:
                    with open('critical_bugs.json', 'r') as f:
                        file_content = f.read()
                    critical_data = extract_json_from_result(file_content)
                    if critical_data and 'issues' in critical_data:
                        print(f"   📊 Found {len(critical_data['issues'])} critical bugs from query")
                        all_bugs.extend(critical_data['issues'])
                    else:
                        print(f"   ⚠️  No critical bugs data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read critical_bugs.json: {e}")
            except Exception as e:
                print(f"   ❌ Error reading bug JSON files: {e}")
            
            print(f"   📊 Found {len(all_bugs)} critical/blocker bugs total")
            
            # Calculate bug metrics programmatically (no LLM needed)
            print(f"   🧮 Calculating bug metrics...")
            bug_metrics_result = calculate_item_metrics(all_bugs, ANALYSIS_PERIOD_DAYS, "bug")
            bug_metrics = bug_metrics_result['metrics']
            recent_activity_bugs = bug_metrics_result['recent_activity_items']
            recently_created_bugs = bug_metrics_result['recently_created_items']
            recently_resolved_bugs = bug_metrics_result['recently_resolved_items']
            
            print(f"   🎯 Bugs with recent activity: {len(recent_activity_bugs)}")
            print(f"   📈 Recently created bugs: {len(recently_created_bugs)}")
            print(f"   ✅ Recently resolved bugs: {len(recently_resolved_bugs)}")
            
            # Analyze each bug with recent activity (only for detailed summaries)
            bug_analyses = []
            
            for i, bug in enumerate(recent_activity_bugs, 1):
                bug_key = bug.get('key', 'Unknown')
                print(f"   📋 {i}/{len(recent_activity_bugs)} Analyzing {bug_key}...", end="")
               
                try:
                    # Determine which fetcher to use based on bug priority
                    bug_priority = bug.get('priority', '')
                    if bug_priority == '1':  # Blocker bugs
                        fetcher_agent = blocker_bug_fetcher
                    elif bug_priority == '2':  # Critical bugs  
                        fetcher_agent = critical_bug_fetcher
                    else:
                        # For other priorities, use blocker fetcher as fallback
                        fetcher_agent = blocker_bug_fetcher
                    
                    bug_details_task = Task(
                        description=f"""
                        Use get_jira_issue_details to get comprehensive information for bug {bug_key}.
                        
                        Call get_jira_issue_details with:
                        - issue_key='{bug_key}'
                        
                        CRITICAL: Return the complete issue details as VALID JSON.
                        Your response must be parseable JSON, not text description.
                        """,
                        agent=fetcher_agent,
                        expected_output=f"Valid JSON data containing full details for {bug_key} - must be parseable as JSON"
                    )
                    
                    details_crew = Crew(
                        agents=[fetcher_agent],
                        tasks=[bug_details_task],
                        verbose=True
                    )
                    
                    details_result = details_crew.kickoff()
                    bug_details = extract_json_from_result(details_result.tasks_output[0])
                    
                    # Generate analysis summary
                    bug_summary = "No summary available - failed to fetch details"
                    if bug_details and not bug_details.get('error'):
                        analysis_task = Task(
                            description=f"""
                            Analyze this critical/blocker bug and create a comprehensive summary:
                            
                            Bug Details: {json.dumps(bug_details, indent=2)}
                            
                            Create a summary covering:
                            - PROBLEM: What is the issue and its impact?
                            - INVESTIGATION: What analysis/debugging has been done?
                            - RESOLUTION EFFORTS: What attempts have been made to fix it?
                            - CURRENT STATUS: Where does the resolution stand?
                            - CHALLENGES: Any blockers or difficulties in resolution?
                            
                            Focus on technical details, progress, and actionable insights.
                            Keep the summary concise but informative.
                            """,
                            agent=bug_analyzer,
                            expected_output=f"Comprehensive analysis summary for {bug_key}"
                        )
                        
                        analysis_crew = Crew(
                            agents=[bug_analyzer],
                            tasks=[analysis_task],
                            verbose=True
                        )
                        
                        analysis_result = analysis_crew.kickoff()
                        bug_summary = str(analysis_result.tasks_output[0]).strip()
                    
                    # Determine severity label from priority  
                    priority = bug.get('priority', 'Unknown')
                    if priority == '1':
                        severity_label = 'BLOCKER'
                    elif priority == '2':
                        severity_label = 'CRITICAL'
                    else:
                        severity_label = f'Priority {priority}'
                    
                    bug_analyses.append({
                        'key': bug_key,
                        'summary': bug.get('summary', 'No summary'),
                        'priority': severity_label,
                        'status': bug.get('status', 'Unknown'),
                        'created': format_timestamp(bug.get('created', '')),
                        'updated': format_timestamp(bug.get('updated', '')),
                        'resolution_date': format_timestamp(bug.get('resolution_date', '')),
                        'analysis': bug_summary
                    })
                    
                    print(" ✅ Done")
                    
                except Exception as e:
                    print(f" ❌ Error: {str(e)[:30]}...")
            
            # Step 3: Analyze epic progress for significant changes
            print(f"\n🎯 Step 3: Analyzing epic progress for significant changes and achievements...")
            
            epic_progress_analyzer = create_epic_progress_analyzer()
            
            # Read the epic summaries file content
            with open(epic_summaries_filename, 'r', encoding='utf-8') as f:
                epic_content = f.read()
            
            # Create task to analyze epic progress
            epic_analysis_task = Task(
                description=f"""
                Analyze the following epic summaries to identify which epics show significant changes, 
                progress, or developments that would be important for stakeholders to know about.
                
                Epic Summaries Content:
                {epic_content}
                
                Your analysis should:
                
                 1. FILTER: Identify which epics have significant progress, changes, or developments
                    (not just routine updates). Look for:
                    - Major features completed or significant milestones reached
                    - Important technical breakthroughs or solutions implemented
                    - Critical issues resolved or major blockers removed
                    - New capabilities delivered or architectural improvements
                    - Significant progress toward business objectives
                    - **IMPORTANT: Always include epics that mention being resolved, completed, or finished - these are significant achievements**
                
                2. ACHIEVEMENTS: For the significant epics, summarize the key achievements:
                    - What major work was completed?
                    - What business value was delivered?
                    - What technical capabilities were added?
                    - What problems were solved?
                
                3. NEXT STEPS: Identify what needs to be done next:
                    - What are the immediate priorities?
                    - What blockers need to be addressed?
                    - What dependencies need to be resolved?
                    - What resources or decisions are needed?
                
                                 Structure your response clearly with sections for:
                 - EPICS WITH SIGNIFICANT PROGRESS (list the epic keys and brief reason)
                 - KEY ACHIEVEMENTS SUMMARY
                 - PRIORITY NEXT STEPS
                 
                 CRITICAL: Do NOT filter out epics that mention being resolved, completed, or finished.
                 These represent important achievements that leadership needs to see.
                 
                 Focus on insights that would help leadership understand progress and make decisions.
                 Be concise but comprehensive.
                """,
                agent=epic_progress_analyzer,
                expected_output="Analysis of epic progress highlighting significant changes, achievements, and next steps"
            )
            
            # Execute epic analysis
            epic_analysis_crew = Crew(
                agents=[epic_progress_analyzer],
                tasks=[epic_analysis_task],
                verbose=True
            )
            
            epic_analysis_result = epic_analysis_crew.kickoff()
            epic_progress_analysis = str(epic_analysis_result.tasks_output[0]).strip()
            
            print("✅ Epic progress analysis completed")
            
            # Save epic progress analysis to separate file
            epic_analysis_filename = 'epic_progress_analysis.txt'
            
            with open(epic_analysis_filename, 'w', encoding='utf-8') as f:
                f.write("KONFLUX EPIC PROGRESS ANALYSIS\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source: Analysis of {len(epic_summaries)} epic summaries\n")
                f.write("=" * 80 + "\n\n")
                f.write(epic_progress_analysis)
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("END OF ANALYSIS\n")
            
            print(f"✅ Epic progress analysis saved to: {epic_analysis_filename}")
            
            # Step 4: Generate bugs analysis file
            print(f"\n🐛 Step 4: Generating bugs analysis file...")
            
            try:
                bugs_filename = 'konflux_bugs_analysis.txt'
                
                with open(bugs_filename, 'w', encoding='utf-8') as f:
                     f.write("KONFLUX CRITICAL/BLOCKER BUGS ANALYSIS\n")
                     f.write("=" * 80 + "\n")
                     f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                     f.write(f"Analysis Period: Last {ANALYSIS_PERIOD_DAYS} days\n")
                     f.write("=" * 80 + "\n\n")
                     
                     # Write calculated metrics
                     f.write("BUG METRICS SUMMARY:\n")
                     f.write("-" * 20 + "\n")
                     f.write(f"Total Blocker Bugs (Priority 1): {bug_metrics['total_blocker_bugs']}\n")
                     f.write(f"Total Critical Bugs (Priority 2): {bug_metrics['total_critical_bugs']}\n")
                     f.write(f"Blocker Bugs Resolved: {bug_metrics['total_blocker_bugs_resolved']}\n")
                     f.write(f"Critical Bugs Resolved: {bug_metrics['total_critical_bugs_resolved']}\n")
                     f.write(f"Blocker Bugs with Recent Activity: {bug_metrics['blocker_bugs_recent_activity']}\n")
                     f.write(f"Critical Bugs with Recent Activity: {bug_metrics['critical_bugs_recent_activity']}\n")
                     f.write(f"Recently Created Blocker Bugs: {bug_metrics['blocker_bugs_created_recently']}\n")
                     f.write(f"Recently Created Critical Bugs: {bug_metrics['critical_bugs_created_recently']}\n")
                     f.write(f"Recently Resolved Blocker Bugs: {bug_metrics['blocker_bugs_resolved_recently']}\n")
                     f.write(f"Recently Resolved Critical Bugs: {bug_metrics['critical_bugs_resolved_recently']}\n\n")
                     
                     if recent_activity_bugs:
                         print(f"   🔍 Processing {len(recent_activity_bugs)} bugs with recent activity...")
                         # Debug: Check structure of first bug
                         if recent_activity_bugs:
                             print(f"   🐛 First bug structure: {list(recent_activity_bugs[0].keys())}")
                         
                         # Group by priority for detailed analysis
                         blockers = [b for b in recent_activity_bugs if b.get('priority') == 'BLOCKER']
                         criticals = [b for b in recent_activity_bugs if b.get('priority') == 'CRITICAL']
                     
                     f.write(f"BUGS WITH RECENT ACTIVITY ({len(recent_activity_bugs)} total):\n")
                     f.write(f"- Blocker bugs: {len(blockers)}\n")
                     f.write(f"- Critical bugs: {len(criticals)}\n\n")
                     
                     # Write recently created bugs
                     if recently_created_bugs:
                         f.write("RECENTLY CREATED BUGS:\n")
                         f.write("-" * 25 + "\n\n")
                         
                         for i, bug in enumerate(recently_created_bugs, 1):
                             f.write(f"{i}. {bug['key']} - {bug.get('priority', 'Unknown')}\n")
                             f.write(f"   Title: {bug['summary']}\n")
                             f.write(f"   Priority: {bug.get('priority', 'Unknown')}\n")
                             f.write(f"   Created: {bug['created']}\n")
                             f.write("\n" + "-" * 30 + "\n\n")
                     
                     # Write recently resolved bugs
                     if recently_resolved_bugs:
                         f.write("RECENTLY RESOLVED BUGS:\n")
                         f.write("-" * 25 + "\n\n")
                         
                         for i, bug in enumerate(recently_resolved_bugs, 1):
                             f.write(f"{i}. {bug['key']} - {bug.get('priority', 'Unknown')}\n")
                             f.write(f"   Title: {bug['summary']}\n")
                             f.write(f"   Priority: {bug.get('priority', 'Unknown')}\n")
                             f.write(f"   Resolved: {bug['resolution_date']}\n")
                             f.write("\n" + "-" * 30 + "\n\n")
                     
                     # Write detailed analysis for bugs with LLM summaries (if any)
                     if bug_analyses:
                         f.write("DETAILED BUG ANALYSIS (With LLM Summaries):\n")
                         f.write("-" * 45 + "\n\n")
                         
                         for i, bug in enumerate(bug_analyses, 1):
                             f.write(f"{i}. {bug['key']} - {bug.get('priority', 'Unknown')}\n")
                             f.write(f"   Title: {bug['summary']}\n")
                             f.write(f"   Status: {bug['status']}\n")
                             f.write(f"   Created: {bug['created']}\n")
                             f.write(f"   Updated: {bug['updated']}\n")
                             f.write(f"   Resolution: {bug['resolution_date']}\n")
                             f.write(f"\n   ANALYSIS:\n")
                             # Indent the analysis for better readability
                             analysis_lines = bug['analysis'].split('\n')
                             for line in analysis_lines:
                                 if line.strip():
                                     f.write(f"   {line}\n")
                             f.write("\n" + "-" * 40 + "\n\n")
                     else:
                         f.write("No critical or blocker bugs found with recent activity.\n\n")
                 
                     f.write("=" * 80 + "")
                     f.write("END OF BUGS ANALYSIS")
             
            except Exception as e:
                print(f"❌ Error in Step 4: {str(e)}")
                import traceback
                traceback.print_exc()
                return
            
            print(f"✅ Bugs analysis saved to: {bugs_filename}")
            
            # Step 5: Fetch and analyze stories and tasks
            print(f"\n📋 Step 5: Analyzing stories and tasks from KONFLUX (last {ANALYSIS_PERIOD_DAYS} days)...")
            
            # Fetch stories (issue_type=17)
            print("   📖 Fetching stories (issue_type=17)...")
            stories_task = Task(
                description="""
                Use list_jira_issues to get all STORY issues from KONFLUX project:
                
                Call list_jira_issues with:
                - project='KONFLUX'
                - issue_type='17' (Story)
                - timeframe=14
                - limit=100
                
                CRITICAL: Return the complete list of stories as VALID JSON.
                Your response must be parseable JSON, not text description.
                Ensure the response contains the exact JSON structure returned by the MCP tool.
                """,
                agent=story_fetcher,
                expected_output="Valid JSON data containing KONFLUX story issues - must be parseable as JSON",
                output_file="stories.json"
            )
            
            # Fetch tasks (issue_type=3)
            print("   📝 Fetching tasks (issue_type=3)...")
            tasks_task = Task(
                description="""
                Use list_jira_issues to get all TASK issues from KONFLUX project:
                
                Call list_jira_issues with:
                - project='KONFLUX'
                - issue_type='3' (Task)
                - timeframe=14
                - limit=100
                
                CRITICAL: Return the complete list of tasks as VALID JSON.
                Your response must be parseable JSON, not text description.
                Ensure the response contains the exact JSON structure returned by the MCP tool.
                """,
                agent=task_fetcher,
                expected_output="Valid JSON data containing KONFLUX task issues - must be parseable as JSON",
                output_file="tasks.json"
            )
            
            # Execute stories and tasks fetching
            stories_tasks_crew = Crew(
                agents=[story_fetcher, task_fetcher],
                tasks=[stories_task, tasks_task],
                verbose=True
            )
            
            stories_tasks_result = stories_tasks_crew.kickoff()
            
            # Process fetched stories and tasks using task outputs (like full_epic_activity_analysis.py)
            all_stories_tasks = []
            
            # Read stories and tasks from the JSON files created by the agents and extract clean JSON
            try:
                # Process stories from JSON file
                try:
                    with open('stories.json', 'r') as f:
                        file_content = f.read()
                    stories_data = extract_json_from_result(file_content)
                    if stories_data and 'issues' in stories_data:
                        print(f"   📊 Found {len(stories_data['issues'])} stories from query")
                        for story in stories_data['issues']:
                            story['item_type'] = 'STORY'
                            all_stories_tasks.append(story)
                    else:
                        print(f"   ⚠️  No stories data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read stories.json: {e}")
                
                # Process tasks from JSON file
                try:
                    with open('tasks.json', 'r') as f:
                        file_content = f.read()
                    tasks_data = extract_json_from_result(file_content)
                    if tasks_data and 'issues' in tasks_data:
                        print(f"   📊 Found {len(tasks_data['issues'])} tasks from query")
                        for task in tasks_data['issues']:
                            task['item_type'] = 'TASK'
                            all_stories_tasks.append(task)
                    else:
                        print(f"   ⚠️  No tasks data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read tasks.json: {e}")
            except Exception as e:
                print(f"   ❌ Error reading stories/tasks JSON files: {e}")
            
            print(f"   📊 Found {len(all_stories_tasks)} stories/tasks total")
            
            # Filter for recent activity
            recent_stories_tasks = []
            
            # Process stories and tasks - no need for manual date filtering 
            # since database timeframe=14 already returned only items with recent activity
            for item in all_stories_tasks:
                recent_stories_tasks.append({
                    'key': item.get('key', 'Unknown'),
                    'summary': item.get('summary', 'No summary'),
                    'item_type': item.get('item_type', 'Unknown'),
                    'status': item.get('status', 'Unknown'),
                    'priority': item.get('priority', 'Unknown'),
                    'updated': format_timestamp(item.get('updated', '')),
                    'created': format_timestamp(item.get('created', '')),
                    'resolution_date': format_timestamp(item.get('resolution_date', ''))
                })
            
            print(f"   🎯 Found {len(recent_stories_tasks)} stories/tasks with recent activity")
            
            # Calculate stories and tasks metrics programmatically
            print(f"   🧮 Calculating stories and tasks metrics...")
            stories_metrics_result = calculate_item_metrics(all_stories_tasks, ANALYSIS_PERIOD_DAYS, "stories_tasks")
            stories_tasks_metrics = stories_metrics_result['metrics']
            
            # Generate stories and tasks analysis file
            stories_tasks_filename = 'konflux_stories_tasks_analysis.txt'
            
            with open(stories_tasks_filename, 'w', encoding='utf-8') as f:
                f.write("KONFLUX STORIES AND TASKS ANALYSIS\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Analysis Period: Last {ANALYSIS_PERIOD_DAYS} days\n")
                f.write("=" * 80 + "\n\n")
                
                # Write summary metrics (calculated programmatically)
                stories = [item for item in recent_stories_tasks if item['item_type'] == 'STORY']
                tasks = [item for item in recent_stories_tasks if item['item_type'] == 'TASK']
                
                f.write("SUMMARY METRICS:\n")
                f.write("-" * 25 + "\n")
                f.write(f"Total Stories/Tasks Found: {stories_tasks_metrics['total_items']}\n")
                f.write(f"Total Resolved Items: {stories_tasks_metrics['total_resolved_items']}\n")
                f.write(f"Items with Recent Activity: {stories_tasks_metrics['items_recent_activity']}\n")
                f.write(f"Recently Created Items: {stories_tasks_metrics['items_created_recently']}\n")
                f.write(f"Recently Resolved Items: {stories_tasks_metrics['items_resolved_recently']}\n\n")
                
                f.write("PRIORITY BREAKDOWN:\n")
                f.write("-" * 20 + "\n")
                for priority, count in stories_tasks_metrics['priority_breakdown'].items():
                    f.write(f"Priority {priority}: {count} items\n")
                f.write("\n")
                
                f.write("BREAKDOWN BY TYPE:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Stories with Recent Activity: {len(stories)}\n")
                f.write(f"Tasks with Recent Activity: {len(tasks)}\n")
                f.write(f"Total Recent Activity Items: {len(recent_stories_tasks)}\n\n")
                
                if recent_stories_tasks:
                    # Write stories section
                    if stories:
                        f.write("STORIES WITH RECENT ACTIVITY:\n")
                        f.write("-" * 35 + "\n\n")
                        
                        for i, story in enumerate(stories, 1):
                            f.write(f"{i}. {story['key']} - STORY\n")
                            f.write(f"   Title: {story['summary']}\n")
                            f.write(f"   Status: {story['status']}\n")
                            f.write(f"   Priority: {story['priority']}\n")
                            f.write(f"   Created: {story['created']}\n")
                            f.write(f"   Updated: {story['updated']}\n")
                            f.write(f"   Resolution: {story['resolution_date']}\n")
                            f.write("\n" + "-" * 40 + "\n\n")
                    
                    # Write tasks section
                    if tasks:
                        f.write("TASKS WITH RECENT ACTIVITY:\n")
                        f.write("-" * 30 + "\n\n")
                        
                        for i, task in enumerate(tasks, 1):
                            f.write(f"{i}. {task['key']} - TASK\n")
                            f.write(f"   Title: {task['summary']}\n")
                            f.write(f"   Status: {task['status']}\n")
                            f.write(f"   Priority: {task['priority']}\n")
                            f.write(f"   Created: {task['created']}\n")
                            f.write(f"   Updated: {task['updated']}\n")
                            f.write(f"   Resolution: {task['resolution_date']}\n")
                            f.write("\n" + "-" * 40 + "\n\n")
                else:
                    f.write("No stories or tasks found with recent activity.\n\n")
                
                f.write("=" * 80 + "\n")
                f.write("END OF STORIES AND TASKS ANALYSIS\n")
            
            print(f"✅ Stories and tasks analysis saved to: {stories_tasks_filename}")
            
            # Step 5a: Generate LLM analysis for stories and tasks with recent activity
            print(f"\n🤖 Step 5a: Generating LLM analysis for stories/tasks with recent activity...")
            
            story_task_analyzer = create_story_task_analyzer(mcp_tools)
            story_task_analyses = []
            
            if len(recent_stories_tasks) > 0:
                print(f"   📊 Analyzing {len(recent_stories_tasks)} stories/tasks with LLM...")
                
                for i, item in enumerate(recent_stories_tasks, 1):
                    item_key = item.get('key', 'Unknown')
                    item_type = item.get('item_type', 'Unknown')
                    print(f"   📋 {i}/{len(recent_stories_tasks)} Analyzing {item_key} ({item_type})...", end="")
                   
                    try:
                        # Get detailed item information
                        # Use appropriate fetcher based on item type
                        if item_type == 'STORY':
                            fetcher_agent = story_fetcher
                        elif item_type == 'TASK':
                            fetcher_agent = task_fetcher
                        else:
                            # Fallback for other types - use story fetcher as it's more general
                            fetcher_agent = story_fetcher
                            
                        item_details_task = Task(
                            description=f"""
                            Use get_jira_issue_details to get comprehensive information for {item_type.lower()} {item_key}.
                            
                            Call get_jira_issue_details with:
                            - issue_key='{item_key}'
                            
                            CRITICAL: Return the complete issue details as VALID JSON.
                            Your response must be parseable JSON, not text description.
                            """,
                            agent=fetcher_agent,
                            expected_output=f"Valid JSON data containing full details for {item_key} - must be parseable as JSON"
                        )
                        
                        details_crew = Crew(
                            agents=[fetcher_agent],
                            tasks=[item_details_task],
                            verbose=True
                        )
                        
                        details_result = details_crew.kickoff()
                        item_details = extract_json_from_result(details_result.tasks_output[0])
                        
                        # Generate analysis summary
                        item_summary = "No summary available - failed to fetch details"
                        if item_details and not item_details.get('error'):
                            analysis_task = Task(
                                description=f"""
                                Analyze this {item_type.lower()} and create a comprehensive summary:
                                
                                {item_type} Details: {json.dumps(item_details, indent=2)}
                                
                                Create a summary covering:
                                - PURPOSE: What functionality or work does this represent?
                                - PROGRESS: What has been accomplished and what's the current status?
                                - IMPLEMENTATION: What technical work has been done?
                                - CHALLENGES: Any blockers or difficulties encountered?
                                - NEXT STEPS: What remains to be done?
                                
                                Focus on technical details, business value, and actionable insights.
                                Keep the summary concise but informative.
                                """,
                                agent=story_task_analyzer,
                                expected_output=f"Comprehensive analysis summary for {item_key}"
                            )
                            
                            analysis_crew = Crew(
                                agents=[story_task_analyzer],
                                tasks=[analysis_task],
                                verbose=True
                            )
                            
                            analysis_result = analysis_crew.kickoff()
                            item_summary = str(analysis_result.tasks_output[0]).strip()
                        
                        story_task_analyses.append({
                            'key': item_key,
                            'summary': item.get('summary', 'No summary'),
                            'item_type': item_type,
                            'status': item.get('status', 'Unknown'),
                            'priority': item.get('priority', 'Unknown'),
                            'created': format_timestamp(item.get('created', '')),
                            'updated': format_timestamp(item.get('updated', '')),
                            'resolution_date': format_timestamp(item.get('resolution_date', '')),
                            'analysis': item_summary
                        })
                        
                        print(" ✅ Done")
                        
                    except Exception as e:
                        print(f" ❌ Error: {str(e)[:30]}...")
                        
                print(f"   ✅ Generated {len(story_task_analyses)} LLM analyses for stories/tasks")
                
                # Update the stories/tasks file with LLM analyses
                print(f"   📝 Adding LLM analyses to {stories_tasks_filename}...")
                
                with open(stories_tasks_filename, 'a', encoding='utf-8') as f:
                    f.write("\n\n" + "=" * 80 + "\n")
                    f.write("LLM ANALYSIS OF STORIES AND TASKS\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total items analyzed: {len(story_task_analyses)}\n")
                    f.write("=" * 80 + "\n\n")
                    
                    if story_task_analyses:
                        for i, analysis in enumerate(story_task_analyses, 1):
                            f.write(f"{i}. {analysis['key']} - {analysis['item_type']}\n")
                            f.write("-" * 60 + "\n")
                            f.write(f"Title: {analysis['summary']}\n")
                            f.write(f"Status: {analysis['status']}\n")
                            f.write(f"Priority: {analysis['priority']}\n")
                            f.write(f"Created: {analysis['created']}\n")
                            f.write(f"Updated: {analysis['updated']}\n")
                            f.write(f"Resolution: {analysis['resolution_date']}\n\n")
                            f.write("DETAILED ANALYSIS:\n")
                            f.write(analysis['analysis'])
                            f.write("\n\n" + "=" * 60 + "\n\n")
                    else:
                        f.write("No items were successfully analyzed.\n\n")
                    
                    f.write("=" * 80 + "\n")
                    f.write("END OF LLM ANALYSIS\n")
                
                print(f"   ✅ LLM analyses added to {stories_tasks_filename}")
            else:
                print("   ℹ️  No stories or tasks with recent activity found for LLM analysis")
            
            # Step 6: Generate consolidated summary (epics only)
            print(f"\n📄 Step 6: Generating consolidated summary...")
            
            output_filename = 'konflux_consolidated_summary.txt'
            
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write("KONFLUX CONSOLIDATED SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Analysis Period: Last {ANALYSIS_PERIOD_DAYS} days\n")
                f.write(f"Note: See '{bugs_filename}' for detailed bugs analysis\n")
                f.write("=" * 80 + "\n\n")
                
                # Epic Progress Analysis (Filtered for Significant Changes)
                f.write("EPIC PROGRESS ANALYSIS - SIGNIFICANT CHANGES & ACHIEVEMENTS\n")
                f.write("=" * 70 + "\n\n")
                f.write(epic_progress_analysis)
                f.write("\n\n" + "=" * 70 + "\n\n")
                
                f.write("=" * 80 + "\n")
                f.write("END OF SUMMARY\n")
            
            print(f"✅ Consolidated summary saved to: {output_filename}")
            
            # Summary statistics
            print(f"\n📊 SUMMARY STATISTICS:")
            print(f"   📋 Epic summaries processed: {len(epic_summaries)}")
            print(f"   🎯 Epic progress analysis completed: Yes")
            print(f"   🐛 Total blocker bugs found: {bug_metrics['total_blocker_bugs']}")
            print(f"   🐛 Total critical bugs found: {bug_metrics['total_critical_bugs']}")
            print(f"   🚨 Blocker bugs with recent activity: {bug_metrics['blocker_bugs_recent_activity']}")
            print(f"   ⚠️  Critical bugs with recent activity: {bug_metrics['critical_bugs_recent_activity']}")
            print(f"   📈 Recently created bugs: {len(recently_created_bugs)}")
            print(f"   ✅ Recently resolved bugs: {len(recently_resolved_bugs)}")
            print(f"   🤖 Detailed LLM analyses: {len(bug_analyses)}")
            print(f"   📊 Total stories/tasks found: {stories_tasks_metrics['total_items']}")
            print(f"   📋 Stories with recent activity: {len([item for item in recent_stories_tasks if item['item_type'] == 'STORY'])}")
            print(f"   📝 Tasks with recent activity: {len([item for item in recent_stories_tasks if item['item_type'] == 'TASK'])}")
            print(f"   📈 Recently created items: {stories_tasks_metrics['items_created_recently']}")
            print(f"   ✅ Recently resolved items: {stories_tasks_metrics['items_resolved_recently']}")
            print(f"   🤖 Story/task LLM analyses: {len(story_task_analyses) if 'story_task_analyses' in locals() else 0}")
            print(f"   📅 Analysis period: Last {ANALYSIS_PERIOD_DAYS} days")
            print(f"\n📄 OUTPUT FILES:")
            print(f"   📄 Consolidated summary (epics): {output_filename}")
            print(f"   📝 Epic summaries only: {epic_summaries_filename}")
            print(f"   🎯 Epic progress analysis: {epic_analysis_filename}")
            print(f"   🐛 Bugs analysis: {bugs_filename}")
            print(f"   📋 Stories & tasks analysis: {stories_tasks_filename}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main() 