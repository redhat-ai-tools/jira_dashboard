#!/usr/bin/env python3
"""
Bugs Analysis Generator
Fetches and analyzes critical/blocker bugs from specified project.
Generates: {project}_bugs_analysis.txt with detailed bug analysis.
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

# Configure Gemini LLM
gemini_api_key = os.getenv("GEMINI_API_KEY")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=gemini_api_key,
    temperature=0.1,
)

# MCP Server configuration
server_params = {
    "url": url,
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": snowflake_token
    }
}

def main(analysis_period_days=14, projects=None):
    """Main function to analyze critical/blocker bugs
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 14)
        projects (list): List of JIRA project keys to analyze (required)
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    print(f"🐛 Multi-Project Bugs Analysis Generator")
    print("="*80)
    print(f"📋 This will analyze critical/blocker bugs from {len(projects)} project(s): {', '.join(projects)}")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output files: [project]_bugs_analysis.txt for each project")
    print("="*80)
    
    # Process each project
    for i, project in enumerate(projects, 1):
        print(f"\n🔍 Processing project {i}/{len(projects)}: {project}")
        print("=" * 60)
        
        try:
            analyze_single_project(analysis_period_days, project)
            print(f"✅ {project} analysis completed successfully")
        except Exception as e:
            print(f"❌ Error analyzing {project}: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"⏭️  Continuing with next project...")
    
    print(f"\n🎉 Multi-project analysis complete! Processed {len(projects)} projects.")

def analyze_single_project(analysis_period_days, project):
    """Analyze bugs for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
    """
    print(f"🐛 {project} Bugs Analysis")
    print(f"📋 Analyzing critical/blocker bugs from {project} project")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output file: {project.lower()}_bugs_analysis.txt")
    
    if not gemini_api_key:
        print("⚠️  Warning: GEMINI_API_KEY environment variable not set")
        return
    
    try:
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create all agents from YAML configuration
            agents = create_agents(mcp_tools, llm)
            
            # Load tasks configuration
            tasks_config = load_tasks_config()
            
            # Step 1: Fetch and analyze critical/blocker bugs
            print(f"\n🐛 Step 1: Analyzing critical/blocker bugs from {project} (last {analysis_period_days} days)...")
            
            # Fetch critical bugs (priority 1 - Blocker)
            print("   🔍 Fetching blocker bugs (priority=1)...")
            blocker_task = create_task_from_config("blocker_task", tasks_config['tasks']['blocker_task'], agents, timeframe=analysis_period_days, project=project, project_lower=project.lower())
            
            # Fetch critical bugs (priority 2 - Critical)
            print("   🔍 Fetching critical bugs (priority=2)...")
            critical_task = create_task_from_config("critical_task", tasks_config['tasks']['critical_task'], agents, timeframe=analysis_period_days, project=project, project_lower=project.lower())
            
            # Execute bug fetching
            bug_crew = Crew(
                agents=[agents['blocker_bug_fetcher'], agents['critical_bug_fetcher']],
                tasks=[blocker_task, critical_task],
                verbose=True
            )
            
            bug_result = bug_crew.kickoff()
            
            # Process fetched bugs using task outputs
            all_bugs = []
            
            # Read bugs from the JSON files created by the agents and extract clean JSON
            try:
                # Process blocker bugs from project-specific JSON file
                blocker_json_file = f'{project.lower()}_blocker_bugs.json'
                try:
                    with open(blocker_json_file, 'r') as f:
                        file_content = f.read()
                    blocker_data = extract_json_from_result(file_content)
                    if blocker_data and 'issues' in blocker_data:
                        print(f"   📊 Found {len(blocker_data['issues'])} blocker bugs from query")
                        all_bugs.extend(blocker_data['issues'])
                    else:
                        print(f"   ⚠️  No blocker bugs data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read {blocker_json_file}: {e}")
                
                # Process critical bugs from project-specific JSON file
                critical_json_file = f'{project.lower()}_critical_bugs.json'
                try:
                    with open(critical_json_file, 'r') as f:
                        file_content = f.read()
                    critical_data = extract_json_from_result(file_content)
                    if critical_data and 'issues' in critical_data:
                        print(f"   📊 Found {len(critical_data['issues'])} critical bugs from query")
                        all_bugs.extend(critical_data['issues'])
                    else:
                        print(f"   ⚠️  No critical bugs data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read {critical_json_file}: {e}")
            except Exception as e:
                print(f"   ❌ Error reading bug JSON files: {e}")
            
            print(f"   📊 Found {len(all_bugs)} critical/blocker bugs total")
            
            # Calculate bug metrics programmatically (no LLM needed)
            print(f"   🧮 Calculating bug metrics...")
            bug_metrics_result = calculate_item_metrics(all_bugs, analysis_period_days, "bug")
            bug_metrics = bug_metrics_result['metrics']
            recent_activity_bugs = bug_metrics_result['recent_activity_items']
            recently_created_bugs = bug_metrics_result['recently_created_items']
            recently_resolved_bugs = bug_metrics_result['recently_resolved_items']
            
            print(f"   🎯 Bugs with recent activity: {len(recent_activity_bugs)}")
            print(f"   📈 Recently created bugs: {len(recently_created_bugs)}")
            print(f"   ✅ Recently resolved bugs: {len(recently_resolved_bugs)}")
            
            # Step 2: Analyze each bug with recent activity (only for detailed summaries)
            print(f"\n🤖 Step 2: Generating detailed LLM analysis for bugs with recent activity...")
            bug_analyses = []
            
            if recent_activity_bugs:
                # Collect all bug keys for batch processing
                bug_keys = [bug.get('key', 'Unknown') for bug in recent_activity_bugs]
                print(f"   🚀 Batch fetching details for {len(bug_keys)} bugs...")
                
                try:
                    # Use batch task to get all bug details at once
                    batch_details_task = create_task_from_config(
                        "batch_bug_details_task", 
                        tasks_config['tasks']['templates']['batch_bug_details_task'], 
                        agents,
                        bug_keys=bug_keys,
                        fetcher_agent='blocker_bug_fetcher'  # Use one agent for batch call
                    )
                    
                    batch_crew = Crew(
                        agents=[agents['blocker_bug_fetcher']],
                        tasks=[batch_details_task],
                        verbose=True
                    )
                    
                    batch_result = batch_crew.kickoff()
                    all_bug_details = extract_json_from_result(batch_result.tasks_output[0])
                    
                    print(f"   ✅ Batch fetch completed! Processing individual analyses...")
                    
                    # Now process each bug individually for analysis
                    for i, bug in enumerate(recent_activity_bugs, 1):
                        bug_key = bug.get('key', 'Unknown')
                        print(f"   📋 {i}/{len(recent_activity_bugs)} Analyzing {bug_key}...", end="")
                       
                        try:
                            # Get the details from batch result
                            bug_details = None
                            if all_bug_details and 'found_issues' in all_bug_details:
                                bug_details = all_bug_details['found_issues'].get(bug_key)
                            
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
                            print(f" ❌ Error: {str(e)}")
                            import traceback
                            print(f"   🐛 Debug traceback: {traceback.format_exc()}")
                            
                except Exception as e:
                    print(f"   ❌ Batch fetch failed: {str(e)}")
                    print("   🔄 Falling back to individual calls...")
                    
                    # Fallback to individual calls if batch fails
                    for i, bug in enumerate(recent_activity_bugs, 1):
                        bug_key = bug.get('key', 'Unknown')
                        print(f"   📋 {i}/{len(recent_activity_bugs)} Analyzing {bug_key} (fallback)...", end="")
                       
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
                            print(f" ❌ Error: {str(e)}")
                            import traceback
                            print(f"   🐛 Debug traceback: {traceback.format_exc()}")
            
            # Step 3: Generate bugs analysis file
            print(f"\n📄 Step 3: Generating bugs analysis file...")
            
            try:
                bugs_filename = f'{project.lower()}_bugs_analysis.txt'
                
                with open(bugs_filename, 'w', encoding='utf-8') as f:
                     f.write(f"{project} CRITICAL/BLOCKER BUGS ANALYSIS\n")
                     f.write("=" * 80 + "\n")
                     f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                     f.write(f"Analysis Period: Last {analysis_period_days} days\n")
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
                 
                     f.write("=" * 80 + "\n")
                     f.write("END OF BUGS ANALYSIS\n")
            
            except Exception as e:
                print(f"❌ Error in Step 3: {str(e)}")
                import traceback
                traceback.print_exc()
                return
            
            print(f"✅ Bugs analysis saved to: {bugs_filename}")
            
            # Summary statistics
            print(f"\n📊 SUMMARY STATISTICS:")
            print(f"   🐛 Total blocker bugs found: {bug_metrics['total_blocker_bugs']}")
            print(f"   🐛 Total critical bugs found: {bug_metrics['total_critical_bugs']}")
            print(f"   🚨 Blocker bugs with recent activity: {bug_metrics['blocker_bugs_recent_activity']}")
            print(f"   ⚠️  Critical bugs with recent activity: {bug_metrics['critical_bugs_recent_activity']}")
            print(f"   📈 Recently created bugs: {len(recently_created_bugs)}")
            print(f"   ✅ Recently resolved bugs: {len(recently_resolved_bugs)}")
            print(f"   🤖 Detailed LLM analyses: {len(bug_analyses)}")
            print(f"   📅 Analysis period: Last {analysis_period_days} days")
            print(f"\n📄 OUTPUT FILE:")
            print(f"   🐛 Bugs analysis: {bugs_filename}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise  # Re-raise to be handled by the multi-project loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate critical/blocker bugs analysis for one or more projects')
    parser.add_argument('--days', '-d', type=int, default=14, 
                       help='Number of days to look back for analysis (default: 14)')
    parser.add_argument('--project', '-p', type=str, required=True,
                       help='JIRA project key(s) to analyze - single project or comma-separated list (e.g., "PROJ1" or "PROJ1,PROJ2,PROJ3")')
    
    args = parser.parse_args()
    
    # Parse projects - handle both single and comma-separated
    if ',' in args.project:
        projects = [p.strip() for p in args.project.split(',') if p.strip()]
    else:
        projects = [args.project.strip()]
    
    main(analysis_period_days=args.days, projects=projects)

