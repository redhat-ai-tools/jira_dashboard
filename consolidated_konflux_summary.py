#!/usr/bin/env python3
"""
Consolidated KONFLUX Summary Generator
Reads the recently_updated_epics_summary.txt file and creates a consolidated summary containing:
1. Epic-level summaries only (extracted from existing file)
2. Critical/blocker bugs analysis from KONFLUX project (last 14 days)
"""

import os
import json
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
    extract_json_from_result,
    parse_epic_summaries
)

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
            
            # Create all agents from YAML configuration
            agents = create_agents(mcp_tools, llm)
            
            # Load tasks configuration
            tasks_config = load_tasks_config()
            
            # Fetch critical bugs (priority 1 - Blocker)
            print("   🔍 Fetching blocker bugs (priority=1)...")
            blocker_task = create_task_from_config("blocker_task", tasks_config['tasks']['blocker_task'], agents)
            
            # Fetch critical bugs (priority 2 - Critical)
            print("   🔍 Fetching critical bugs (priority=2)...")
            critical_task = create_task_from_config("critical_task", tasks_config['tasks']['critical_task'], agents)
            
            # Execute bug fetching
            bug_crew = Crew(
                agents=[agents['blocker_bug_fetcher'], agents['critical_bug_fetcher']],
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
                        fetcher_agent_name = 'blocker_bug_fetcher'
                    elif bug_priority == '2':  # Critical bugs  
                        fetcher_agent_name = 'critical_bug_fetcher'
                    else:
                        # For other priorities, use blocker fetcher as fallback
                        fetcher_agent_name = 'blocker_bug_fetcher'
                    
                    bug_details_task = create_task_from_config(
                        "bug_details_task", 
                        tasks_config['tasks']['templates']['bug_details_task'], 
                        agents,
                        bug_key=bug_key,
                        fetcher_agent=fetcher_agent_name
                    )
                    
                    details_crew = Crew(
                        agents=[agents[fetcher_agent_name]],
                        tasks=[bug_details_task],
                        verbose=True
                    )
                    
                    details_result = details_crew.kickoff()
                    bug_details = extract_json_from_result(details_result.tasks_output[0])
                    
                    # Generate analysis summary
                    bug_summary = "No summary available - failed to fetch details"
                    if bug_details and not bug_details.get('error'):
                        analysis_task = create_task_from_config(
                            "bug_analysis_task",
                            tasks_config['tasks']['templates']['bug_analysis_task'],
                            agents,
                            bug_details=json.dumps(bug_details, indent=2),
                            bug_key=bug_key
                        )
                        
                        analysis_crew = Crew(
                            agents=[agents['bug_analyzer']],
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
            
            # Read the epic summaries file content
            with open(epic_summaries_filename, 'r', encoding='utf-8') as f:
                epic_content = f.read()
            
            # Create task to analyze epic progress
            epic_analysis_task = create_task_from_config(
                "epic_analysis_task",
                tasks_config['tasks']['epic_analysis_task'],
                agents,
                epic_content=epic_content
            )
            
            # Execute epic analysis
            epic_analysis_crew = Crew(
                agents=[agents['epic_progress_analyzer']],
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
            stories_task = create_task_from_config("stories_task", tasks_config['tasks']['stories_task'], agents)
            
            # Fetch tasks (issue_type=3)
            print("   📝 Fetching tasks (issue_type=3)...")
            tasks_task = create_task_from_config("tasks_task", tasks_config['tasks']['tasks_task'], agents)
            
            # Execute stories and tasks fetching
            stories_tasks_crew = Crew(
                agents=[agents['story_fetcher'], agents['task_fetcher']],
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
                f.write("BREAKDOWN BY TYPE:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Stories with Recent Activity: {len(stories)}\n")
                f.write(f"Tasks with Recent Activity: {len(tasks)}\n")
                f.write(f"Total Recent Activity Items: {len(recent_stories_tasks)}\n\n")
                

            print(f"✅ Stories and tasks analysis saved to: {stories_tasks_filename}")
            
            # Step 5a: Generate LLM analysis for stories and tasks with recent activity
            print(f"\n🤖 Step 5a: Generating LLM analysis for stories/tasks with recent activity...")
            
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