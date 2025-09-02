#!/usr/bin/env python3
"""
Project Dashboard Generator using CrewAI with MCP JIRA Snowflake Tools
Uses real MCP SSE server to fetch project data - NO HARDCODED DATA
"""

import os
import json
import re
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter

# Import helper functions
from helper_func import (
    load_agents_config, load_tasks_config, create_agent_from_config, 
    create_task_from_config, filter_project_summary, 
    BugCalculator, extract_html_from_result
)

# Configure LLM (as recommended in CrewAI SSE documentation)
model_api_key = os.getenv("MODEL_API_KEY")
model_name = os.getenv("MODEL_NAME", "gemini/gemini-2.5-flash")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")

llm = LLM(
    model=model_name,
    api_key=model_api_key,
    temperature=0.7,
)

print(f"🤖 Using model: {model_name}")

# MCP Server configuration for JIRA Snowflake (SSE Server)
# Following the exact pattern from CrewAI MCP documentation
server_params = {
    "url": url,
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": snowflake_token 
    }
}

def create_agents_from_yaml(mcp_tools):
    """Create agents from YAML configuration"""
    agents_config = load_agents_config()
    agents = {}
    
    # Create the specific agents needed for this dashboard
    agent_names = [
        'jira_data_analyst',
        'dashboard_developer', 
        'critical_bug_fetcher',
        'blocker_bug_fetcher',
        'project_summary_analyst'
    ]
    
    for agent_name in agent_names:
        if agent_name in agents_config['agents']:
            config = agents_config['agents'][agent_name]
            agents[agent_name] = create_agent_from_config(agent_name, config, mcp_tools, llm)
    
    return agents

def create_tasks_from_yaml(agents_dict, project, timeframe_days=14):
    """Create tasks from YAML configuration"""
    tasks_config = load_tasks_config()
    tasks = []
    
    # Create the specific tasks needed for this dashboard
    task_names = [
        'fetch_data_task',
        'critical_task',
        'blocker_task', 
        'fetch_project_summary_task',
        'generate_dashboard_task'
    ]
    
    for task_name in task_names:
        if task_name in tasks_config['tasks']:
            config = tasks_config['tasks'][task_name]
            # Pass project parameter, project_lower, and timeframe for template substitution
            task = create_task_from_config(task_name, config, agents_dict, 
                                         project=project, 
                                         project_lower=project.lower(),
                                         timeframe=timeframe_days)
            
            # Set context for generate_dashboard_task
            if task_name == 'generate_dashboard_task':
                task.context = tasks[:-1]  # Reference all previous tasks
            
            tasks.append(task)
    
    return tasks

def main(project=None, timeframe_days=14):
    """Main function to run the CrewAI workflow"""
    if not project:
        raise ValueError("Project parameter is required. Please specify a JIRA project key using --project.")
    
    project = project.upper()  # Normalize to uppercase
    
    try:
        print(f"🚀 Starting {project} Dashboard Generation with CrewAI...")
        print(f"📊 Analysis timeframe: {timeframe_days} days")
        print(f"📡 Connecting to MCP Server: {server_params['url']}")
        
        # Check if model API key is available
        if not model_api_key:
            print("⚠️  Warning: MODEL_API_KEY environment variable not set")
            print("💡 Please set MODEL_API_KEY before running this script")
            create_fallback_dashboard(project)
            return
        
        # Connect to MCP server and get tools using context manager
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create agents and tasks from YAML configurations
            agents_dict = create_agents_from_yaml(mcp_tools)
            tasks_list = create_tasks_from_yaml(agents_dict, project, timeframe_days)
            
            print(f"📋 Created {len(agents_dict)} agents and {len(tasks_list)} tasks from YAML configurations")
            
            # Create and run the crew
            crew = Crew(
                agents=list(agents_dict.values()),
                tasks=tasks_list,
                verbose=True
            )
            
            print("🤖 Starting CrewAI workflow...")
            result = crew.kickoff()
            
            print("📝 Processing CrewAI result...")
            
            # Debug: Check if we have task outputs
            if hasattr(result, 'tasks_output'):
                print(f"📊 Got {len(result.tasks_output)} task results")
                for i, task_output in enumerate(result.tasks_output):
                    print(f"   Task {i+1}: {type(task_output)} - {str(task_output)[:100]}...")
            else:
                print("⚠️  No task outputs found in result")
            
            # Process project summary data if available
            project_summary_data = None
            try:
                # Get the project summary task result (fourth task in the crew)
                if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 4:
                    project_summary_result = result.tasks_output[3]
                    
                    print(f"🔍 Raw project summary result: {str(project_summary_result)[:200]}...")
                    
                    # Try to parse as JSON directly first
                    raw_summary = str(project_summary_result).strip()
                    try:
                        # First try to parse the raw result as JSON
                        import json
                        project_summary_data = json.loads(raw_summary)
                        print("✅ Successfully parsed project summary as direct JSON")
                    except json.JSONDecodeError as e:
                        print(f"⚠️  Direct JSON parsing failed: {e}")
                        print(f"🔧 Trying filter_project_summary function...")
                        # Fall back to the filter function
                        project_summary_data = filter_project_summary(raw_summary, project)
                    
                    if "error" not in project_summary_data:
                        print(f"📊 Project Summary Data:")
                        print(f"   Status Breakdown: {project_summary_data.get('statuses', {})}")
                        print(f"   Priority Breakdown: {project_summary_data.get('priorities', {})}")
                        
                        # Save project summary for potential use
                        with open(f'{project.lower()}_project_summary.json', 'w') as f:
                            json.dump(project_summary_data, f, indent=2)
                    else:
                        print(f"⚠️  Project summary error: {project_summary_data.get('error', 'Unknown error')}")
                else:
                    print("⚠️  Project summary task result not available")
            except Exception as e:
                print(f"⚠️  Error processing project summary data: {e}")
            
            # Create calculators for different priority levels
            critical_calculator = BugCalculator(priority_ids=["2"], priority_name="Critical")
            blocker_calculator = BugCalculator(priority_ids=["1"], priority_name="Blocker")
            
            # Process critical bug data if available (second task in the crew - critical_task)
            try:
                if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 2:
                    critical_bug_result = result.tasks_output[1]
                    
                    # Extract critical bug data
                    critical_bug_data = critical_calculator.extract_json_from_result(critical_bug_result)
                    
                    if critical_bug_data and 'issues' in critical_bug_data:
                        issues = critical_bug_data['issues']
                        metrics, critical_bugs_fixed = critical_calculator.calculate_bug_metrics(issues)
                        
                        print(f"🔥 Critical Bug Metrics:")
                        print(f"   Total Critical Bugs: {metrics['total_critical_bugs']}")
                        print(f"   Total Critical Bugs Resolved: {metrics['total_critical_bugs_resolved']}")
                        print(f"   Critical Bugs Resolved (Last Month): {metrics['critical_bugs_resolved_last_month']}")
                        
                        # Save critical bug metrics for potential use
                        with open('critical_bugs.json', 'w') as f:
                            json.dump({
                                'metrics': metrics,
                                'critical_bugs_fixed': critical_bugs_fixed,
                                'timestamp': datetime.now().isoformat()
                            }, f, indent=2)
                    else:
                        print("⚠️  Could not extract critical bug data")
                else:
                    print("⚠️  Critical bug task result not available")
            except Exception as e:
                print(f"⚠️  Error processing critical bug data: {e}")
            
            # Process blocker bug data if available (third task in the crew - blocker_task)
            try:
                if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 3:
                    blocker_bug_result = result.tasks_output[2]
                    
                    # Extract blocker bug data
                    blocker_bug_data = blocker_calculator.extract_json_from_result(blocker_bug_result)
                    
                    if blocker_bug_data and 'issues' in blocker_bug_data:
                        issues = blocker_bug_data['issues']
                        metrics, blocker_bugs_fixed = blocker_calculator.calculate_bug_metrics(issues)
                        
                        print(f"🚫 Blocker Bug Metrics:")
                        print(f"   Total Blocker Bugs: {metrics['total_blocker_bugs']}")
                        print(f"   Total Blocker Bugs Resolved: {metrics['total_blocker_bugs_resolved']}")
                        print(f"   Blocker Bugs Resolved (Last Month): {metrics['blocker_bugs_resolved_last_month']}")
                        
                        # Save blocker bug metrics for potential use
                        with open('blocker_bugs.json', 'w') as f:
                            json.dump({
                                'metrics': metrics,
                                'blocker_bugs_fixed': blocker_bugs_fixed,
                                'timestamp': datetime.now().isoformat()
                            }, f, indent=2)
                    else:
                        print("⚠️  Could not extract blocker bug data")
                else:
                    print("⚠️  Blocker bug task result not available")
            except Exception as e:
                print(f"⚠️  Error processing blocker bug data: {e}")
            
            # Extract HTML from the result
            html_content = extract_html_from_result(result)
            
            # Fix the critical bug metrics with actual calculated values
            if os.path.exists('critical_bugs.json'):
                try:
                    with open('critical_bugs.json', 'r') as f:
                        bug_metrics = json.load(f)
                    
                    metrics = bug_metrics['metrics']
                    print(f"🔧 Replacing hardcoded critical bug values with calculated metrics:")
                    print(f"   Total Critical Bugs: {metrics['total_critical_bugs']}")
                    print(f"   Total Resolved: {metrics['total_critical_bugs_resolved']}")
                    print(f"   Resolved Last Month: {metrics['critical_bugs_resolved_last_month']}")
                    
                    # Replace the hardcoded JavaScript values with actual calculated values
                    html_content = html_content.replace(
                        "document.getElementById('total-critical').textContent = totalCriticalBugs;",
                        f"document.getElementById('total-critical').textContent = {metrics['total_critical_bugs']};"
                    )
                    html_content = html_content.replace(
                        "document.getElementById('resolved-critical').textContent = totalResolvedCritical;",
                        f"document.getElementById('resolved-critical').textContent = {metrics['total_critical_bugs_resolved']};"
                    )
                    html_content = html_content.replace(
                        "document.getElementById('resolved-last-month').textContent = resolvedLastMonth;",
                        f"document.getElementById('resolved-last-month').textContent = {metrics['critical_bugs_resolved_last_month']};"
                    )
                    
                    # Also replace any hardcoded const values that might override these
                    html_content = re.sub(
                        r'const resolvedLastMonth = \d+;.*',
                        f'const resolvedLastMonth = {metrics["critical_bugs_resolved_last_month"]};',
                        html_content
                    )
                    
                    print("✅ HTML updated with correct calculated critical bug metrics")
                    
                except Exception as e:
                    print(f"⚠️  Could not update HTML with calculated critical bug metrics: {e}")
            else:
                print("⚠️  Critical bugs JSON file not found")
            
            # Fix the blocker bug metrics with actual calculated values
            if os.path.exists('blocker_bugs.json'):
                try:
                    with open('blocker_bugs.json', 'r') as f:
                        blocker_metrics_data = json.load(f)
                    
                    blocker_metrics = blocker_metrics_data['metrics']
                    print(f"🔧 Replacing hardcoded blocker bug values with calculated metrics:")
                    print(f"   Total Blocker Bugs: {blocker_metrics['total_blocker_bugs']}")
                    print(f"   Total Resolved: {blocker_metrics['total_blocker_bugs_resolved']}")
                    print(f"   Resolved Last Month: {blocker_metrics['blocker_bugs_resolved_last_month']}")
                    
                    # Replace the hardcoded JavaScript values with actual calculated values
                    html_content = html_content.replace(
                        "document.getElementById('total-blocker').textContent = totalBlockerBugs;",
                        f"document.getElementById('total-blocker').textContent = {blocker_metrics['total_blocker_bugs']};"
                    )
                    html_content = html_content.replace(
                        "document.getElementById('resolved-blocker').textContent = totalResolvedBlocker;",
                        f"document.getElementById('resolved-blocker').textContent = {blocker_metrics['total_blocker_bugs_resolved']};"
                    )
                    html_content = html_content.replace(
                        "document.getElementById('resolved-blocker-last-month').textContent = resolvedBlockerLastMonth;",
                        f"document.getElementById('resolved-blocker-last-month').textContent = {blocker_metrics['blocker_bugs_resolved_last_month']};"
                    )
                    
                    print("✅ HTML updated with correct calculated blocker bug metrics")
                    
                except Exception as e:
                    print(f"⚠️  Could not update HTML with calculated blocker bug metrics: {e}")
            else:
                print("⚠️  Blocker bugs JSON file not found")
            
            # Save the HTML file
            dashboard_filename = f'{project.lower()}_real_dashboard.html'
            with open(dashboard_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print("✅ Dashboard generation completed!")
            print(f"📊 Dashboard saved as: {dashboard_filename}")
            print(f"📏 HTML file size: {len(html_content)} characters")
            print("🔥 Critical bug metrics included in dashboard")
            print("🚫 Blocker bug metrics included in dashboard")
            
            # Verify the file was created properly
            if os.path.exists(dashboard_filename):
                file_size = os.path.getsize(dashboard_filename)
                print(f"✅ File verification: {file_size} bytes written successfully")
            else:
                print("❌ File verification failed: File not found")
            
            return result
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("💡 Fallback: Creating dashboard with error message...")
        create_fallback_dashboard(project)

def create_fallback_dashboard(project=None):
    """Create a simple dashboard if MCP connection fails"""
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project} Dashboard - Connection Error</title>
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 40px; 
            text-align: center; 
            background: #f5f5f5;
        }}
        .error {{ 
            color: #d32f2f; 
            background: #ffebee; 
            padding: 30px; 
            border-radius: 12px; 
            border-left: 4px solid #d32f2f;
            max-width: 600px;
            margin: 0 auto;
        }}
        h1 {{ margin-bottom: 20px; }}
        p {{ margin: 10px 0; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="error">
        <h1>🔌 MCP Connection Error</h1>
        <p>Could not connect to JIRA Snowflake MCP server.</p>
        <p>Please check your network connection and server configuration.</p>
        <p><strong>Server:</strong> {url}</p>
        <p><strong>API Key:</strong> Please ensure MODEL_API_KEY is set in your environment</p>
    </div>
</body>
</html>'''
    
    fallback_filename = f'{project.lower()}_real_dashboard.html'
    with open(fallback_filename, 'w') as f:
        f.write(html_content)
    print(f"📄 Fallback dashboard created: {fallback_filename}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Generate project dashboard using CrewAI')
    parser.add_argument('--project', '-p', type=str, required=True,
                       help='JIRA project key to analyze (required)')
    parser.add_argument('--days', '-d', type=int, default=14,
                       help='Number of days to look back for analysis (default: 14)')
    
    args = parser.parse_args()
    main(project=args.project, timeframe_days=args.days) 