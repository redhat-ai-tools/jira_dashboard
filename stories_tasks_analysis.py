#!/usr/bin/env python3
"""
Stories and Tasks Analysis Generator
Fetches and analyzes stories and tasks from specified project.
Generates: {project}_stories_tasks_analysis.txt with detailed analysis.
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter
from helper_func import (
    load_agents_config, 
    load_tasks_config, 
    create_agent_from_config,
    create_task_from_config,
    create_agents,
    format_timestamp,
    is_timestamp_within_days,
    calculate_item_metrics,
    extract_json_from_result
)

# Configure LLM
model_api_key = os.getenv("MODEL_API_KEY")
model_name = os.getenv("MODEL_NAME", "gemini/gemini-2.5-flash")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")

llm = LLM(
    model=model_name,
    api_key=model_api_key,
    temperature=0.1,
)

print(f"🤖 Using model: {model_name}")

# MCP Server configuration
server_params = {
    "url": url,
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": snowflake_token
    }
}

def main(analysis_period_days=14, projects=None, components=None):
    """Main function to analyze stories and tasks
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 14)
        projects (list): List of JIRA project keys to analyze (required)
        components (str): Optional comma-separated components to filter by (e.g., 'x,y')
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    print(f"📋 Multi-Project Stories and Tasks Analysis Generator")
    print("="*80)
    print(f"📋 This will analyze stories and tasks from {len(projects)} project(s): {', '.join(projects)}")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output files: [project]_stories_tasks_analysis.txt for each project")
    print("="*80)
    
    # Process each project
    for i, project in enumerate(projects, 1):
        print(f"\n🔍 Processing project {i}/{len(projects)}: {project}")
        print("=" * 60)
        
        try:
            analyze_single_project(analysis_period_days, project, components)
            print(f"✅ {project} analysis completed successfully")
        except Exception as e:
            print(f"❌ Error analyzing {project}: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"⏭️  Continuing with next project...")
    
    print(f"\n🎉 Multi-project analysis complete! Processed {len(projects)} projects.")

def analyze_single_project(analysis_period_days, project, components=None):
    """Analyze stories and tasks for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
        components (str): Optional comma-separated components to filter by
    """
    print(f"📋 {project} Stories and Tasks Analysis")
    print(f"📋 Analyzing stories and tasks from {project} project")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output file: {project.lower()}_stories_tasks_analysis.txt")
    
    if not model_api_key:
        print("⚠️  Warning: MODEL_API_KEY environment variable not set")
        return
    
    try:
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create all agents from YAML configuration
            agents = create_agents(mcp_tools, llm)
            
            # Load tasks configuration
            tasks_config = load_tasks_config()
            
            # Step 1: Fetch and analyze stories and tasks
            print(f"\n📋 Step 1: Analyzing stories and tasks from {project} (last {analysis_period_days} days)...")
            
            # Format components parameter for task templates
            components_param = f"\n- components='{components}'" if components else ""
            
            # Fetch stories (issue_type=17)
            print("   📖 Fetching stories (issue_type=17)...")
            stories_task = create_task_from_config("stories_task", tasks_config['tasks']['stories_task'], agents, timeframe=analysis_period_days, project=project, project_lower=project.lower(), components_param=components_param)
            
            # Fetch tasks (issue_type=3)
            print("   📝 Fetching tasks (issue_type=3)...")
            tasks_task = create_task_from_config("tasks_task", tasks_config['tasks']['tasks_task'], agents, timeframe=analysis_period_days, project=project, project_lower=project.lower(), components_param=components_param)
            
            # Execute stories and tasks fetching
            stories_tasks_crew = Crew(
                agents=[agents['story_fetcher'], agents['task_fetcher']],
                tasks=[stories_task, tasks_task],
                verbose=True
            )
            
            stories_tasks_result = stories_tasks_crew.kickoff()
            
            # Process fetched stories and tasks using task outputs
            all_stories_tasks = []
            
            # Read stories and tasks from the JSON files created by the agents and extract clean JSON
            try:
                # Process stories from project-specific JSON file
                stories_json_file = f'{project.lower()}_stories.json'
                try:
                    with open(stories_json_file, 'r') as f:
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
                    print(f"   ⚠️  Could not read {stories_json_file}: {e}")
                
                # Process tasks from project-specific JSON file
                tasks_json_file = f'{project.lower()}_tasks.json'
                try:
                    with open(tasks_json_file, 'r') as f:
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
                    print(f"   ⚠️  Could not read {tasks_json_file}: {e}")
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
            stories_metrics_result = calculate_item_metrics(all_stories_tasks, analysis_period_days, "stories_tasks")
            stories_tasks_metrics = stories_metrics_result['metrics']
            
            # Step 2: Generate initial analysis file with basic metrics
            stories_tasks_filename = f'{project.lower()}_stories_tasks_analysis.txt'
            
            with open(stories_tasks_filename, 'w', encoding='utf-8') as f:
                f.write(f"{project} STORIES AND TASKS ANALYSIS\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Analysis Period: Last {analysis_period_days} days\n")
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
                f.write("BREAKDOWN BY TYPE:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Stories with Recent Activity: {len(stories)}\n")
                f.write(f"Tasks with Recent Activity: {len(tasks)}\n")
                f.write(f"Total Recent Activity Items: {len(recent_stories_tasks)}\n\n")
            
            print(f"✅ Stories and tasks analysis saved to: {stories_tasks_filename}")
            
            # Step 3: Generate LLM analysis for stories and tasks with recent activity
            print(f"\n🤖 Step 3: Generating LLM analysis for stories/tasks with recent activity...")
            
            story_task_analyses = []
            
            if len(recent_stories_tasks) > 0:
                print(f"   📊 Analyzing {len(recent_stories_tasks)} stories/tasks with LLM...")
                
                # Collect all item keys for batch processing
                item_keys = [item.get('key', 'Unknown') for item in recent_stories_tasks]
                print(f"   🚀 Batch fetching details for {len(item_keys)} stories/tasks...")
                
                try:
                    # Use batch task to get all item details at once
                    batch_details_task = create_task_from_config(
                        "batch_item_details_task", 
                        tasks_config['tasks']['templates']['batch_item_details_task'], 
                        agents,
                        item_keys=item_keys,
                        fetcher_agent='story_fetcher'  # Use one agent for batch call
                    )
                    
                    batch_crew = Crew(
                        agents=[agents['story_fetcher']],
                        tasks=[batch_details_task],
                        verbose=True
                    )
                    
                    batch_result = batch_crew.kickoff()
                    all_item_details = extract_json_from_result(batch_result.tasks_output[0])
                    
                    print(f"   ✅ Batch fetch completed! Processing individual analyses...")
                    
                    # Now process each item individually for analysis
                    for i, item in enumerate(recent_stories_tasks, 1):
                        item_key = item.get('key', 'Unknown')
                        item_type = item.get('item_type', 'Unknown')
                        print(f"   📋 {i}/{len(recent_stories_tasks)} Analyzing {item_key} ({item_type})...", end="")
                       
                        try:
                            # Get the details from batch result
                            item_details = None
                            if all_item_details and 'found_issues' in all_item_details:
                                item_details = all_item_details['found_issues'].get(item_key)
                            
                            # Generate analysis summary
                            item_summary = "No summary available - failed to fetch details"
                            if item_details and not item_details.get('error'):
                                analysis_task = create_task_from_config(
                                    "item_analysis_task",
                                    tasks_config['tasks']['templates']['item_analysis_task'],
                                    agents,
                                    item_type=item_type,
                                    item_details=json.dumps(item_details, indent=2),
                                    item_key=item_key
                                )
                                
                                analysis_crew = Crew(
                                    agents=[agents['story_task_analyzer']],
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
                            print(f" ❌ Error: {str(e)}")
                            import traceback
                            print(f"   🐛 Debug traceback: {traceback.format_exc()}")
                            
                except Exception as e:
                    print(f"   ❌ Batch fetch failed: {str(e)}")
                    print("   🔄 Falling back to individual calls...")
                    
                    # Fallback to individual calls if batch fails
                    for i, item in enumerate(recent_stories_tasks, 1):
                        item_key = item.get('key', 'Unknown')
                        item_type = item.get('item_type', 'Unknown')
                        print(f"   📋 {i}/{len(recent_stories_tasks)} Analyzing {item_key} ({item_type}) (fallback)...", end="")
                       
                        try:
                            # Get detailed item information
                            # Use appropriate fetcher based on item type
                            if item_type == 'STORY':
                                fetcher_agent_name = 'story_fetcher'
                            elif item_type == 'TASK':
                                fetcher_agent_name = 'task_fetcher'
                            else:
                                # Fallback for other types - use story fetcher as it's more general
                                fetcher_agent_name = 'story_fetcher'
                                
                            item_details_task = create_task_from_config(
                                "item_details_task",
                                tasks_config['tasks']['templates']['item_details_task'],
                                agents,
                                item_type=item_type.lower(),
                                item_key=item_key,
                                fetcher_agent=fetcher_agent_name
                            )
                            
                            details_crew = Crew(
                                agents=[agents[fetcher_agent_name]],
                                tasks=[item_details_task],
                                verbose=True
                            )
                            
                            details_result = details_crew.kickoff()
                            item_details = extract_json_from_result(details_result.tasks_output[0])
                            
                            # Generate analysis summary
                            item_summary = "No summary available - failed to fetch details"
                            if item_details and not item_details.get('error'):
                                analysis_task = create_task_from_config(
                                    "item_analysis_task",
                                    tasks_config['tasks']['templates']['item_analysis_task'],
                                    agents,
                                    item_type=item_type,
                                    item_details=json.dumps(item_details, indent=2),
                                    item_key=item_key
                                )
                                
                                analysis_crew = Crew(
                                    agents=[agents['story_task_analyzer']],
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
                            print(f" ❌ Error: {str(e)}")
                            import traceback
                            print(f"   🐛 Debug traceback: {traceback.format_exc()}")
                        
                print(f"   ✅ Generated {len(story_task_analyses)} LLM analyses for stories/tasks")
                
                # Step 4: Update the stories/tasks file with LLM analyses
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
            
            # Summary statistics
            print(f"\n📊 SUMMARY STATISTICS:")
            print(f"   📊 Total stories/tasks found: {stories_tasks_metrics['total_items']}")
            print(f"   📋 Stories with recent activity: {len([item for item in recent_stories_tasks if item['item_type'] == 'STORY'])}")
            print(f"   📝 Tasks with recent activity: {len([item for item in recent_stories_tasks if item['item_type'] == 'TASK'])}")
            print(f"   📈 Recently created items: {stories_tasks_metrics['items_created_recently']}")
            print(f"   ✅ Recently resolved items: {stories_tasks_metrics['items_resolved_recently']}")
            print(f"   🤖 Story/task LLM analyses: {len(story_task_analyses) if 'story_task_analyses' in locals() else 0}")
            print(f"   📅 Analysis period: Last {analysis_period_days} days")
            print(f"\n📄 OUTPUT FILE:")
            print(f"   📋 Stories & tasks analysis: {stories_tasks_filename}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise  # Re-raise to be handled by the multi-project loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate stories and tasks analysis for one or more projects')
    parser.add_argument('--days', '-d', type=int, default=14, 
                       help='Number of days to look back for analysis (default: 14)')
    parser.add_argument('--project', '-p', type=str, required=True,
                       help='JIRA project key(s) to analyze - single project or comma-separated list (e.g., "PROJ1" or "PROJ1,PROJ2,PROJ3")')
    parser.add_argument('--components', '-c', type=str, default=None,
                       help='Optional comma-separated components to filter by (e.g., "x,y")')
    
    args = parser.parse_args()
    
    # Parse projects - handle both single and comma-separated
    if ',' in args.project:
        projects = [p.strip() for p in args.project.split(',') if p.strip()]
    else:
        projects = [args.project.strip()]
    
    main(analysis_period_days=args.days, projects=projects, components=args.components)

