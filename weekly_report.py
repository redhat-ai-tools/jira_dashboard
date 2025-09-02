#!/usr/bin/env python3
"""
Weekly Accomplishments Report Generator
Fetches and analyzes issues from specified projects to generate weekly accomplishments.
Generates: weekly_accomplishments_report.html with combined report for all projects.
"""

import os
import json
import argparse
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter
from helper_func import (
    load_agents_config, 
    load_tasks_config, 
    create_agent_from_config,
    create_task_from_config,
    create_agents,
    format_timestamp,
    extract_json_from_result,
    calculate_total_issues,
    map_priority,
    map_status,
    map_issue_type,
    add_jira_links_to_html,
    filter_test_issues,
    convert_markdown_to_html,
)

# Configure LLM
model_api_key = os.getenv("MODEL_API_KEY")
model_name = os.getenv("MODEL_NAME", "gemini/gemini-2.5-flash")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")
jira_base_url = os.getenv("JIRA_BASE_URL")
main_project = os.getenv("MAIN_PROJECT")  # Can be None, will be overridden by CLI args if provided

llm = LLM(
    model=model_name,
    api_key=model_api_key,
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

def main(analysis_period_days=7, projects=None, components=None, components_provided=False, main_project_override=None):
    """Main function to generate weekly accomplishments report
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 7)
        projects (list): List of JIRA project keys to analyze (required)
        components (str): Optional comma-separated components to filter by (e.g., 'component-x,component-y')
        components_provided (bool): Whether components were explicitly provided via CLI
        main_project_override (str): Optional main project override (takes precedence over env var)
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    # Use main_project_override if provided, otherwise use environment variable
    effective_main_project = main_project_override or main_project
    
    print(f"📊 Weekly Accomplishments Report Generator")
    print("="*80)
    print(f"📋 This will analyze weekly accomplishments from {len(projects)} project(s): {', '.join(projects)}")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output file: weekly_accomplishments_report.html")
    # Check if any project is the main project
    main_project_in_list = effective_main_project and effective_main_project in projects
    other_projects_exist = effective_main_project and any(effective_main_project != p for p in projects)
    
    if main_project_in_list and other_projects_exist and components_provided:
        print(f"🎯 Enhanced mode: Project bugs + MAIN_PROJECT ({effective_main_project}) component filtering + feature completions")
    elif main_project_in_list and components_provided:
        print(f"🎯 Enhanced mode: MAIN_PROJECT ({effective_main_project}) with component filtering + feature completions")
    elif other_projects_exist and components_provided:
        print(f"🎯 Enhanced mode: Project bugs + MAIN_PROJECT ({effective_main_project}) bugs & feature completions")
    else:
        print(f"🎯 Standard mode: Project bugs only")
    print("="*80)
    
    if not model_api_key:
        print("⚠️  Warning: MODEL_API_KEY environment variable not set")
        return
    
    # Store individual project reports
    project_reports = []
    
    try:
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create all agents from YAML configuration
            agents = create_agents(mcp_tools, llm)
            
            # Load tasks configuration
            tasks_config = load_tasks_config()
            
            # Process each project
            for i, project in enumerate(projects, 1):
                print(f"\n🔍 Processing project {i}/{len(projects)}: {project}")
                print("=" * 60)
                
                try:
                    project_data = analyze_single_project(
                        analysis_period_days, project, components, agents, tasks_config, effective_main_project, projects, components_provided
                    )
                    print(f"🔍 DEBUG: project_data type for {project}: {type(project_data)}")
                    print(f"🔍 DEBUG: project_data content: {project_data}")
                    project_reports.append({
                        'project': project,
                        'report': project_data['weekly_report'],
                        'bugs': project_data['bugs'],
                        'bug_summary': project_data.get('bug_summary', ''),
                        'feature_completions': project_data.get('feature_completions', []),
                        'total_issues': project_data['total_issues'],
                        'non_bug_count': project_data['non_bug_count'],
                        'bug_count': project_data['bug_count'],
                        'feature_completions_count': project_data.get('feature_completions_count', 0),
                        'success': True
                    })
                    print(f"✅ {project} weekly report completed successfully")
                except Exception as e:
                    print(f"❌ Error analyzing {project}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    project_reports.append({
                        'project': project,
                        'report': f"Error generating report for {project}: {str(e)}",
                        'bugs': [],
                        'bug_summary': '',
                        'feature_completions': [],
                        'total_issues': 0,
                        'non_bug_count': 0,
                        'bug_count': 0,
                        'feature_completions_count': 0,
                        'success': False
                    })
                    print(f"⏭️  Continuing with next project...")
            
            # Generate combined HTML report
            print(f"\n📄 Generating combined weekly accomplishments report...")
            generate_combined_html_report(projects, project_reports, analysis_period_days, components)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise
    
    print(f"\n🎉 Weekly accomplishments report generation complete! Processed {len(projects)} projects.")

def analyze_single_project(analysis_period_days, project, components, agents, tasks_config, main_project=None, projects_list=None, components_provided=False):
    """Analyze weekly accomplishments for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
        components (str): Optional comma-separated components to filter by
        agents (dict): Dictionary of created agents
        tasks_config (dict): Tasks configuration
        main_project (str): Optional main project for bug fetching
        projects_list (list): List of all projects being analyzed
        components_provided (bool): Whether components were explicitly provided via CLI
        
    Returns:
        dict: Weekly accomplishments report and bugs data for the project
    """
    print(f"🔍 DEBUG: Starting analyze_single_project for {project}")
    print(f"🔍 DEBUG: Parameters - days: {analysis_period_days}, components: {components}, main_project: {main_project}")
    print(f"📊 {project} Weekly Accomplishments Analysis")
    print(f"📋 Analyzing issues from {project} project")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    
    # Step 1: Fetch issues updated in the analysis period
    # Use component filtering only if this project is the main project
    use_components_for_main_issues = main_project and project == main_project and components_provided
    
    if use_components_for_main_issues:
        components_param = f"\n- components='{components}'" if components else ""
        print(f"\n📡 Step 1: Fetching issues updated in {project} (main project) with component filtering (last {analysis_period_days} days)...")
    else:
        components_param = ""
        print(f"\n📡 Step 1: Fetching issues updated in {project} (last {analysis_period_days} days)...")
    
    fetch_issues_task = create_task_from_config(
        "fetch_issues_task", 
        tasks_config['tasks']['fetch_issues_task'], 
        agents, 
        project=project, 
        project_lower=project.lower(),
        days=analysis_period_days,
        components_param=components_param
    )
    
    # Execute issue fetching
    fetch_crew = Crew(
        agents=[agents['issues_fetcher']],
        tasks=[fetch_issues_task],
        verbose=True
    )
    
    fetch_result = fetch_crew.kickoff()
    
    # Step 1.5: Conditionally fetch bugs based on MAIN_PROJECT and components configuration
    # Only use main project if BOTH main_project and components were explicitly provided AND project != main_project
    use_main_project = main_project and main_project != project and components_provided
    
    if use_main_project:
        # Extract the component for the current project from the components string
        project_component = get_project_component(project, components, projects_list or [project])
        print(f"\n📡 Step 1.5: Fetching additional bugs from {main_project} with {project_component} component (last {analysis_period_days} days)...")
        
        created_bugs_task = create_task_from_config(
            "created_bugs_task", 
            tasks_config['tasks']['created_bugs_task'], 
            agents, 
            project=project, 
            project_lower=project.lower(),
            days=analysis_period_days,
            main_project=main_project,
            component=project_component
        )
        
        # Execute created bugs fetching
        created_bugs_crew = Crew(
            agents=[agents['created_bugs_fetcher']],
            tasks=[created_bugs_task],
            verbose=True
        )
        
        created_bugs_result = created_bugs_crew.kickoff()
        
        # Step 1.6: Fetch feature completions from main project
        print(f"\n📡 Step 1.6: Fetching feature completions from {main_project} with {project_component} component (last {analysis_period_days} days)...")
        
        feature_completions_task = create_task_from_config(
            "feature_completions_task", 
            tasks_config['tasks']['feature_completions_task'], 
            agents, 
            project=project, 
            project_lower=project.lower(),
            days=analysis_period_days,
            main_project=main_project,
            component=project_component
        )
        
        # Execute feature completions fetching
        feature_completions_crew = Crew(
            agents=[agents['feature_completions_fetcher']],
            tasks=[feature_completions_task],
            verbose=True
        )
        
        feature_completions_result = feature_completions_crew.kickoff()
    else:
        if not main_project:
            print(f"\n📡 Step 1.5: MAIN_PROJECT not provided - will only use bugs from {project} project issues")
        elif not components_provided:
            print(f"\n📡 Step 1.5: Components not explicitly provided - will only use bugs from {project} project issues")
        elif main_project == project:
            print(f"\n📡 Step 1.5: Current project is the main project - already using component filtering in Step 1")
        else:
            print(f"\n📡 Step 1.5: Will only use bugs from {project} project issues")
    
    # Process fetched issues
    all_issues = []
    
    # Read issues from the JSON file created by the agent
    try:
        issues_json_file = f'{project.lower()}_recent_issues.json'
        try:
            with open(issues_json_file, 'r') as f:
                file_content = f.read()
            issues_data = extract_json_from_result(file_content)
            if issues_data and 'issues' in issues_data:
                all_issues = issues_data['issues']
                print(f"   📊 Found {len(all_issues)} issues with recent activity")
            else:
                print(f"   ⚠️  No issues data or empty result")
        except (FileNotFoundError, Exception) as e:
            print(f"   ⚠️  Could not read {issues_json_file}: {e}")
    except Exception as e:
        print(f"   ❌ Error reading issues JSON file: {e}")
    

    
    if not all_issues:
        print(f"   ⚠️  No issues found for analysis.")
        return {
            'weekly_report': f"No issues found with activity in the last {analysis_period_days} days for {project}.",
            'bugs': [],
            'bug_summary': '',
            'feature_completions': [],
            'total_issues': 0,
            'non_bug_count': 0,
            'bug_count': 0,
            'feature_completions_count': 0
        }
    
    # Step 2: Fetch detailed issue information
    print(f"\n📡 Step 2: Fetching detailed issue information...")
    
    # Use all issues for detailed analysis
    analysis_issues = all_issues
    issue_keys = [issue.get('key', 'Unknown') for issue in analysis_issues]
    
    print(f"   🚀 Batch fetching details for {len(issue_keys)} issues...")
    
    detailed_issues = []
    try:
        # Use batch task to get all issue details at once
        batch_details_task = create_task_from_config(
            "batch_item_details_task", 
            tasks_config['tasks']['templates']['batch_item_details_task'], 
            agents,
            item_keys=issue_keys,
            fetcher_agent='issues_fetcher'
        )
        
        batch_crew = Crew(
            agents=[agents['issues_fetcher']],
            tasks=[batch_details_task],
            verbose=True
        )
        
        batch_result = batch_crew.kickoff()
        all_issue_details = extract_json_from_result(batch_result.tasks_output[0])
        
        print(f"   ✅ Batch fetch completed! Processing detailed data...")
        
        # Prepare detailed issues data for analysis
        for issue in analysis_issues:
            issue_key = issue.get('key', 'Unknown')
            
            # Get the detailed info from batch result
            detailed_info = None
            if all_issue_details and 'found_issues' in all_issue_details:
                detailed_info = all_issue_details['found_issues'].get(issue_key)
            
            # Create enriched issue data
            enriched_issue = {
                'key': issue_key,
                'summary': issue.get('summary', 'No summary'),
                'issue_type': issue.get('issue_type', 'Unknown'),
                'priority': issue.get('priority', 'Unknown'),
                'status': issue.get('status', 'Unknown'),
                'component': issue.get('component', []),
                'created': issue.get('created', ''),
                'updated': issue.get('updated', '')
            }
            
            # Add detailed information if available
            if detailed_info and not detailed_info.get('error'):
                enriched_issue['description'] = detailed_info.get('description', '')
                enriched_issue['comments'] = detailed_info.get('comments', [])
                enriched_issue['labels'] = detailed_info.get('labels', [])
                enriched_issue['links'] = detailed_info.get('links', [])
                
                # Add recent comments summary for analysis
                comments = detailed_info.get('comments', [])
                if comments:
                    recent_comments = comments[-3:] if len(comments) > 3 else comments
                    comment_text = ' | '.join([comment.get('body', '') for comment in recent_comments if comment.get('body')])
                    enriched_issue['recent_comments_summary'] = comment_text
                else:
                    enriched_issue['recent_comments_summary'] = ''
            else:
                # Fallback to basic data
                enriched_issue['description'] = issue.get('description', '')
                enriched_issue['comments'] = []
                enriched_issue['labels'] = []
                enriched_issue['links'] = []
                enriched_issue['recent_comments_summary'] = ''
            
            detailed_issues.append(enriched_issue)
        
        print(f"   📊 Prepared {len(detailed_issues)} detailed issues for analysis")
        
    except Exception as e:
        print(f"   ❌ Batch fetch failed: {str(e)}")
        print("   🔄 Falling back to basic issue data...")
        
        # Fallback to basic data if batch fails
        for issue in analysis_issues:
            detailed_issues.append({
                'key': issue.get('key', 'Unknown'),
                'summary': issue.get('summary', 'No summary'),
                'description': issue.get('description', ''),
                'issue_type': issue.get('issue_type', 'Unknown'),
                'priority': issue.get('priority', 'Unknown'),
                'status': issue.get('status', 'Unknown'),
                'component': issue.get('component', []),
                'created': issue.get('created', ''),
                'updated': issue.get('updated', ''),
                'comments': [],
                'labels': [],
                'links': [],
                'recent_comments_summary': ''
            })
    
    # Filter out test issues before analysis
    print(f"\n🧹 Step 2.5: Filtering out test issues...")
    detailed_issues = filter_test_issues(detailed_issues)
    print(f"   📊 Remaining issues after filtering: {len(detailed_issues)}")
    
    # Step 3: Separate bugs from non-bugs and optionally add bugs from main project
    print(f"\n🔄 Step 3: Separating bugs from other issues...")
    bugs = []
    non_bugs = []
    
    # Always use original behavior: separate bugs and non-bugs from detailed_issues
    print(f"   🔄 Extracting bugs from {project} project issues...")
    print(f"   🔍 DEBUG: detailed_issues type: {type(detailed_issues)}, length: {len(detailed_issues)}")
    
    for i, issue in enumerate(detailed_issues):
        print(f"   🔍 DEBUG: Issue {i} type: {type(issue)}")
        if isinstance(issue, dict):
            issue_type = issue.get('issue_type', 'Unknown')
            if str(issue_type) == '1':  # Bug type = 1
                bugs.append(issue)
            else:
                non_bugs.append(issue)
        else:
            print(f"   ❌ ERROR: Issue {i} is not a dict, it's {type(issue)}: {issue}")
            # Skip non-dict items
            continue
    
    print(f"   🐛 Found {len(bugs)} bugs from {project} project")
    
    # Additionally get bugs from the created bugs agent if MAIN_PROJECT is configured
    if use_main_project:
        # Get the component for this project (defined earlier in Step 1.5)
        project_component = get_project_component(project, components, projects_list or [project])
        print(f"   🔄 Additionally getting bugs from {main_project} with {project_component} component...")
        additional_bugs = []
        try:
            created_bugs_json_file = f'{project.lower()}_created_bugs.json'
            try:
                with open(created_bugs_json_file, 'r') as f:
                    file_content = f.read()
                print(f"   🔍 DEBUG: Created bugs file content type: {type(file_content)}")
                print(f"   🔍 DEBUG: Created bugs file content (first 200 chars): {file_content[:200]}")
                bugs_data = json.loads(file_content)
                print(f"   🔍 DEBUG: Parsed bugs_data type: {type(bugs_data)}")
                print(f"   🔍 DEBUG: Parsed bugs_data keys: {bugs_data.keys() if isinstance(bugs_data, dict) else 'Not a dict'}")
                if bugs_data and 'issues' in bugs_data:
                    additional_bugs = bugs_data['issues']
                    print(f"   🐛 Found {len(additional_bugs)} additional bugs from {main_project} with {project_component} component")
                    # Add additional bugs to the main bugs list
                    bugs.extend(additional_bugs)
                else:
                    print(f"   ⚠️  No additional bugs data or empty result")
            except (FileNotFoundError, Exception) as e:
                print(f"   ⚠️  Could not read {created_bugs_json_file}: {e}")
        except Exception as e:
            print(f"   ❌ Error reading created bugs JSON file: {e}")
    
    print(f"   🐛 Total bugs found: {len(bugs)}")
    print(f"   📋 Non-bug issues: {len(non_bugs)}")
    
    # Step 3.5: Generate bug summary if bugs exist
    bug_summary = ""
    if bugs:
        print(f"\n🤖 Step 3.5: Generating bug analysis summary...")
        try:
            # Get detailed bug information
            bug_keys = [bug.get('key', 'Unknown') for bug in bugs]
            print(f"   🚀 Batch fetching details for {len(bug_keys)} bugs...")
            
            batch_bug_details_task = create_task_from_config(
                "batch_item_details_task", 
                tasks_config['tasks']['templates']['batch_item_details_task'], 
                agents,
                item_keys=bug_keys,
                fetcher_agent='bug_fetcher'
            )
            
            batch_bug_crew = Crew(
                agents=[agents['bug_fetcher']],
                tasks=[batch_bug_details_task],
                verbose=True
            )
            
            batch_bug_result = batch_bug_crew.kickoff()
            bug_details_data = extract_json_from_result(batch_bug_result.tasks_output[0])
            
            print(f"   ✅ Bug details fetch completed! Generating summary...")
            
            # Generate bug summary
            bug_summary_task = create_task_from_config(
                "bugs_summary_analysis_task",
                tasks_config['tasks']['templates']['bugs_summary_analysis_task'],
                agents,
                bugs_data=json.dumps(bug_details_data, indent=2)
            )
            
            bug_summary_crew = Crew(
                agents=[agents['bugs_summary_analyst']],
                tasks=[bug_summary_task],
                verbose=True
            )
            
            bug_summary_result = bug_summary_crew.kickoff()
            bug_summary = str(bug_summary_result.tasks_output[0]).strip()
            
            print(f"   ✅ Bug summary generated ({len(bug_summary)} chars)")
            
        except Exception as e:
            print(f"   ❌ Bug analysis failed: {str(e)}")
            bug_summary = ""
    else:
        print(f"\n📊 Step 3.5: No bugs found - skipping bug analysis")
    
    # Step 4: Prepare data for weekly accomplishments analysis
    print(f"\n🤖 Step 4: Preparing data for weekly accomplishments analysis...")
    
    # Get feature completions data if available
    feature_completions = []
    if use_main_project:
        print(f"   🔄 Processing feature completions from {main_project}...")
        try:
            feature_completions_json_file = f'{project.lower()}_feature_completions.json'
            try:
                with open(feature_completions_json_file, 'r') as f:
                    file_content = f.read()
                print(f"   🔍 DEBUG: Feature completions file content type: {type(file_content)}")
                print(f"   🔍 DEBUG: Feature completions file content (first 200 chars): {file_content[:200]}")
                completions_data = json.loads(file_content)
                print(f"   🔍 DEBUG: Parsed completions_data type: {type(completions_data)}")
                print(f"   🔍 DEBUG: Parsed completions_data keys: {completions_data.keys() if isinstance(completions_data, dict) else 'Not a dict'}")
                if completions_data and 'issues' in completions_data:
                    feature_completions = completions_data['issues']
                    print(f"   ✅ Found {len(feature_completions)} feature completions from {main_project}")
                else:
                    print(f"   ⚠️  No feature completions data or empty result")
            except (FileNotFoundError, Exception) as e:
                print(f"   ⚠️  Could not read {feature_completions_json_file}: {e}")
        except Exception as e:
            print(f"   ❌ Error reading feature completions JSON file: {e}")
    
    # Combine non-bugs with feature completions for comprehensive analysis
    analysis_data = non_bugs.copy() if non_bugs else []
    print(f"   🔍 DEBUG: non_bugs type: {type(non_bugs)}, length: {len(non_bugs)}")
    print(f"   🔍 DEBUG: feature_completions type: {type(feature_completions)}, length: {len(feature_completions)}")
    if feature_completions:
        analysis_data.extend(feature_completions)
        print(f"   📊 Combined {len(non_bugs)} non-bug issues + {len(feature_completions)} feature completions = {len(analysis_data)} total items for analysis")
    else:
        print(f"   📊 Using {len(analysis_data)} non-bug issues for analysis")
    print(f"   🔍 DEBUG: analysis_data type: {type(analysis_data)}, length: {len(analysis_data)}")
    
    # Generate weekly accomplishments analysis
    print(f"\n🤖 Step 4.5: Generating weekly accomplishments analysis...")
    
    if analysis_data:
        analysis_task = create_task_from_config(
            "weekly_accomplishments_analysis_task",
            tasks_config['tasks']['templates']['weekly_accomplishments_analysis_task'],
            agents,
            project=project,
            issues_data=json.dumps(analysis_data, indent=2)
        )
        
        analysis_crew = Crew(
            agents=[agents['weekly_report_analyst']],
            tasks=[analysis_task],
            verbose=True
        )
        
        analysis_result = analysis_crew.kickoff()
        weekly_report = str(analysis_result.tasks_output[0]).strip()
        
        print(f"   ✅ Weekly accomplishments analysis completed ({len(weekly_report)} chars)")
    else:
        weekly_report = "No non-bug issues or feature completions found for analysis."
        print(f"   ⚠️  No analysis data found")
    
    # Summary statistics
    print(f"\n📊 SUMMARY STATISTICS:")
    print(f"   📋 Total issues analyzed: {len(detailed_issues)}")
    print(f"   🐛 Bugs found: {len(bugs)}")
    print(f"   📋 Non-bug issues analyzed: {len(non_bugs)}")
    if use_main_project and feature_completions:
        print(f"   🎯 Feature completions found: {len(feature_completions)}")
    print(f"   🕒 Analysis period: Last {analysis_period_days} days")
    print(f"   🧩 Components filter: {components if components else 'None'}")
    if use_main_project:
        project_component = get_project_component(project, components, projects_list or [project])
        print(f"   🎯 Bug sources: {project} project + {main_project} project with {project_component} component")
        print(f"   🎯 Feature sources: {main_project} project with {project_component} component")
    elif use_components_for_main_issues:
        print(f"   🎯 Bug source: {project} project (main project) with component filtering")
    else:
        print(f"   🎯 Bug source: {project} project only")
    
    return {
        'weekly_report': weekly_report,
        'bugs': bugs,
        'bug_summary': bug_summary,
        'feature_completions': feature_completions,
        'total_issues': len(detailed_issues),
        'non_bug_count': len(non_bugs),
        'bug_count': len(bugs),
        'feature_completions_count': len(feature_completions)
    }

def generate_combined_html_report(projects, project_reports, analysis_period_days, components):
    """Generate combined HTML report for all projects"""
    
    components_display = f"<strong>Components:</strong> {components}" if components else "<strong>Components:</strong> All"
    
    # Build project sections
    project_sections = []
    for report_data in project_reports:
        project = report_data['project']
        report = report_data['report']
        success = report_data['success']
        bugs = report_data.get('bugs', [])
        bug_count = report_data.get('bug_count', 0)
        bug_summary = report_data.get('bug_summary', '')
        
        if success:
            # Convert markdown to HTML if needed
            report_html = convert_markdown_to_html(report)
            # Add JIRA links to the HTML content
            report_html = add_jira_links_to_html(report_html, project, jira_base_url)
            
            # Generate bugs table if there are bugs
            bugs_section = ""
            if bugs:
                # Separate bugs into open and resolved/closed
                open_bugs = []
                resolved_bugs = []
                
                for bug in bugs:
                    status = bug.get('status', 'Unknown')
                    status_label = map_status(status)
                    
                    # Check if bug is resolved/closed (status 6 = Resolved/Closed)
                    if str(status) == '6' or 'resolved' in status_label.lower() or 'closed' in status_label.lower():
                        resolved_bugs.append(bug)
                    else:
                        open_bugs.append(bug)
                
                bugs_table_rows = ""
                
                # Add open bugs first
                for bug in open_bugs:
                    bug_key = bug.get('key', 'Unknown')
                    bug_link = f"{jira_base_url}{bug_key}" if jira_base_url else f"#{bug_key}"
                    bug_title = bug.get('summary', 'No summary')
                    
                    # Map IDs to human-readable labels using helper functions
                    status_label = map_status(bug.get('status', 'Unknown'))
                    priority_label = map_priority(bug.get('priority', 'Unknown'))
                    
                    bugs_table_rows += f"""
                    <tr>
                        <td><a href="{bug_link}" target="_blank" class="jira-link">{bug_key}</a></td>
                        <td>{bug_title}</td>
                        <td>{status_label}</td>
                        <td>{priority_label}</td>
                    </tr>
                    """
                
                # Add separator row if we have both open and resolved bugs
                if open_bugs and resolved_bugs:
                    bugs_table_rows += f"""
                    <tr class="bugs-separator">
                        <td colspan="4" class="separator-cell">
                            <div class="separator-line"></div>
                            <span class="separator-text">Resolved/Closed Issues ({len(resolved_bugs)})</span>
                            <div class="separator-line"></div>
                        </td>
                    </tr>
                    """
                
                # Add resolved bugs
                for bug in resolved_bugs:
                    bug_key = bug.get('key', 'Unknown')
                    bug_link = f"{jira_base_url}{bug_key}" if jira_base_url else f"#{bug_key}"
                    bug_title = bug.get('summary', 'No summary')
                    
                    # Map IDs to human-readable labels using helper functions
                    status_label = map_status(bug.get('status', 'Unknown'))
                    priority_label = map_priority(bug.get('priority', 'Unknown'))
                    
                    bugs_table_rows += f"""
                    <tr class="resolved-bug">
                        <td><a href="{bug_link}" target="_blank" class="jira-link">{bug_key}</a></td>
                        <td>{bug_title}</td>
                        <td>{status_label}</td>
                        <td>{priority_label}</td>
                    </tr>
                    """
                
                # Add bug summary above the table if available
                bug_summary_html = ""
                if bug_summary:
                    bug_summary_html = f"""
                    <div class="bug-summary">
                        <p>{bug_summary}</p>
                    </div>
                    """
                
                # Create header with open vs total count
                open_count = len(open_bugs)
                total_count = len(bugs)
                bugs_header = f"🐛 Bugs ({open_count} open, {total_count} total)"
                
                bugs_section = f"""
                <div class="bugs-section">
                    <h3>{bugs_header}</h3>
                    {bug_summary_html}
                    <div class="table-container">
                        <table class="bugs-table">
                            <thead>
                                <tr>
                                    <th>Issue Key</th>
                                    <th>Summary</th>
                                    <th>Status</th>
                                    <th>Priority</th>
                                </tr>
                            </thead>
                            <tbody>
                                {bugs_table_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
                """
            else:
                bugs_section = f"""
                <div class="bugs-section">
                    <h3>🐛 Bugs</h3>
                    <p><em>No bugs found in the analysis period.</em></p>
                </div>
                """

        else:
            report_html = f'<div class="error-message">⚠️ {report}</div>'
            bugs_section = ""
        
        project_section = f"""
        <div class="project-section">
            <h2 class="project-header">[{project}]</h2>
            <div class="project-content">
                {report_html}
                {bugs_section}
            </div>
        </div>
        """
        project_sections.append(project_section)
    
    projects_list = ', '.join(projects)
    all_project_sections = '\n'.join(project_sections)
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Accomplishments Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
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
            text-align: center;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }}
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .meta-info {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .meta-info h3 {{
            margin-top: 0;
            color: #495057;
        }}
        .project-section {{
            margin: 40px 0;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            overflow: hidden;
        }}
        .project-header {{
            background: #6c757d;
            color: white;
            padding: 15px 25px;
            margin: 0;
            font-size: 1.5em;
            font-weight: bold;
        }}
        .project-content {{
            padding: 25px;
        }}
        .project-content h1, .project-content h2, .project-content h3 {{
            color: #495057;
            margin-top: 25px;
            margin-bottom: 15px;
        }}
        .project-content h1 {{
            color: #2c7be5;
            margin: 0 0 30px 0;
            font-size: 1.7em;
            border-bottom: 3px solid #667eea;
            padding-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 600;
        }}
        .project-content h1:before {{
            content: "🎯";
            font-size: 1.3em;
        }}
        .project-content h2 {{
            color: #495057;
            margin: 40px 0 25px 0;
            font-size: 1.4em;
            font-weight: 600;
            padding: 20px 25px;
            background: linear-gradient(135deg, #e8f2ff 0%, #f0f7ff 100%);
            border-left: 5px solid #667eea;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            box-shadow: 0 3px 10px rgba(102, 126, 234, 0.1);
        }}
        .project-content h2:before {{
            content: "🔹";
            font-size: 1.2em;
            color: #667eea;
        }}
        .project-content h3 {{
            color: #6c757d;
            margin: 30px 0 20px 0;
            font-size: 1.2em;
            font-weight: 600;
            padding: 15px 20px;
            background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
            border-left: 4px solid #6c757d;
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 2px 8px rgba(108, 117, 125, 0.1);
        }}
        .project-content h3:before {{
            content: "▶";
            font-size: 0.9em;
            color: #6c757d;
        }}
        .project-content ul {{
            margin: 25px 0;
            padding: 0;
            list-style: none;
        }}
        .project-content li {{
            margin: 12px 0;
            padding: 20px 25px;
            background: white;
            border-radius: 12px;
            border-left: 5px solid #667eea;
            line-height: 1.8;
            box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08);
            position: relative;
            transition: all 0.3s ease;
            font-size: 1.05em;
        }}
        .project-content li:hover {{
            transform: translateX(8px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.2);
        }}
        .project-content li:before {{
            content: "●";
            color: #667eea;
            font-weight: bold;
            position: absolute;
            left: 8px;
            top: 30px;
            font-size: 12px;
        }}
        .project-content strong {{
            color: #495057;
            font-weight: 600;
        }}
        .project-content p {{
            margin: 20px 0;
            line-height: 1.8;
            color: #444;
            font-size: 1.05em;
        }}
        .project-content a {{
            color: #667eea;
            font-weight: 500;
            text-decoration: none;
            padding: 2px 4px;
            border-radius: 3px;
            background: rgba(102, 126, 234, 0.1);
            transition: all 0.2s ease;
        }}
        .project-content a:hover {{
            background: rgba(102, 126, 234, 0.2);
            text-decoration: none;
        }}
        .project-content .highlight-box {{
            background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%);
            border: 1px solid #0066cc;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #0066cc;
        }}
        .project-content .success-box {{
            background: linear-gradient(135deg, #e6ffe6 0%, #f5fff5 100%);
            border: 1px solid #00cc66;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #00cc66;
        }}
        .project-content .warning-box {{
            background: linear-gradient(135deg, #fff2e6 0%, #fffaf5 100%);
            border: 1px solid #ff6600;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #ff6600;
        }}
        .accomplishment-category {{
            background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
            border: 1px solid #e9ecef;
            border-radius: 12px;
            padding: 25px;
            margin: 25px 0;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            border-left: 6px solid #667eea;
        }}
        .accomplishment-category h2 {{
            margin-top: 0;
            margin-bottom: 20px;
            color: #2c7be5;
            font-size: 1.3em;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .accomplishment-category h3 {{
            margin-top: 0;
            margin-bottom: 20px;
            color: #495057;
            font-size: 1.2em;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .error-message {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }}
        .jira-link {{
            color: #0052cc;
            text-decoration: none;
            font-weight: 500;
        }}
        .jira-link:hover {{
            text-decoration: underline;
        }}
        .bugs-section {{
            margin: 30px 0;
            background: #fff9f9;
            border: 1px solid #ffebee;
            border-radius: 8px;
            padding: 20px;
        }}
        .bugs-section h3 {{
            color: #d32f2f;
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 1.2em;
        }}
        .bug-summary {{
            background: #f8f9fa;
            border-left: 4px solid #d32f2f;
            border-radius: 4px;
            padding: 15px;
            margin: 15px 0;
            font-style: italic;
            color: #5a5a5a;
            line-height: 1.6;
        }}
        .bug-summary p {{
            margin: 0;
        }}
        .bugs-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .bugs-table th {{
            background-color: #d32f2f;
            color: white;
            font-weight: 600;
            padding: 12px;
            text-align: left;
        }}
        .bugs-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .bugs-table tr:hover {{
            background-color: #fafafa;
        }}
        .bugs-table tr:last-child td {{
            border-bottom: none;
        }}
        .bugs-separator {{
            background: #f8f9fa !important;
        }}
        .bugs-separator:hover {{
            background: #f8f9fa !important;
        }}
        .separator-cell {{
            padding: 15px 12px !important;
            text-align: center;
            border-top: 2px solid #dee2e6;
            border-bottom: 2px solid #dee2e6;
        }}
        .separator-cell .separator-line {{
            display: inline-block;
            width: 30%;
            height: 1px;
            background: #6c757d;
            vertical-align: middle;
        }}
        .separator-text {{
            display: inline-block;
            padding: 0 15px;
            font-weight: 600;
            color: #6c757d;
            font-size: 0.9em;
            vertical-align: middle;
        }}
        .resolved-bug {{
            opacity: 0.7;
            background: #f8f9fa;
        }}
        .resolved-bug:hover {{
            opacity: 1;
            background: #e9ecef;
        }}
        
        /* Print styles */
        @media print {{
            body {{
                background-color: white;
            }}
            .container {{
                box-shadow: none;
                margin: 0;
                padding: 20px;
            }}
            .header {{
                background: #667eea !important;
                -webkit-print-color-adjust: exact;
            }}
            .project-header {{
                background: #6c757d !important;
                -webkit-print-color-adjust: exact;
            }}
        }}
        
        /* Responsive design */
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                padding: 20px;
            }}
            .header {{
                margin: -20px -20px 20px -20px;
                padding: 20px;
            }}
            .header h1 {{
                font-size: 2em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Weekly Accomplishments Report</h1>
            <div class="subtitle">Team Progress and Achievements Summary</div>
        </div>

        <div class="meta-info">
            <h3>📋 Report Details</h3>
            <p><strong>Projects Analyzed:</strong> {projects_list}</p>
            <p><strong>Analysis Period:</strong> Last {analysis_period_days} days</p>
            <p>{components_display}</p>
            <p><strong>Report Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        {all_project_sections}

        <div class="footer">
            <p>Report generated by JIRA Weekly Accomplishments System | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Save combined report
    html_filename = 'weekly_accomplishments_report.html'
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Combined weekly accomplishments report saved to: {html_filename}")

def get_component_for_project(project):
    """
    Get the component name for a given project.
    
    Uses the following priority:
    1. PROJECT_COMPONENT_MAPPING environment variable (JSON format)
    2. Individual PROJECT_NAME_COMPONENT environment variables
    3. Falls back to project name as component
    
    Args:
        project (str): Project name
        
    Returns:
        str: Component name for the project
    """
    # Try PROJECT_COMPONENT_MAPPING environment variable (JSON format)
    mapping_env = os.getenv("PROJECT_COMPONENT_MAPPING")
    if mapping_env:
        try:
            import json
            mapping = json.loads(mapping_env)
            if project in mapping:
                return mapping[project]
        except (json.JSONDecodeError, KeyError):
            print(f"⚠️  Warning: Invalid PROJECT_COMPONENT_MAPPING format, ignoring...")
    
    # Try individual PROJECT_NAME_COMPONENT environment variables
    component_env_var = f"{project.upper()}_COMPONENT"
    component = os.getenv(component_env_var)
    if component:
        return component
    
    # Fall back to project name as component
    return project

def get_project_component(project, components_string, projects_list):
    """
    Get the component for a specific project based on positional mapping.
    
    Components are mapped to projects by position:
    - projects[0] -> components[0]
    - projects[1] -> components[1] 
    - etc.
    
    Args:
        project (str): The project name to find component for
        components_string (str): Comma-separated components string
        projects_list (list): List of all projects being analyzed
        
    Returns:
        str: Component name for the project
    """
    if not components_string:
        return get_component_for_project(project)
    
    # Split components 
    components = [c.strip() for c in components_string.split(',') if c.strip()]
    
    # If only one component, use it for all projects
    if len(components) == 1:
        return components[0]
    
    # Find the position of the current project in the projects list
    try:
        project_index = projects_list.index(project)
        
        # If we have a component for this position, use it
        if project_index < len(components):
            return components[project_index]
        else:
            # More projects than components - use the last component
            print(f"⚠️  Warning: More projects than components. Using last component '{components[-1]}' for {project}")
            return components[-1]
            
    except ValueError:
        # Project not found in list (shouldn't happen)
        print(f"⚠️  Warning: Project {project} not found in projects list, using first component: {components[0]}")
        return components[0]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate weekly accomplishments report for one or more projects')
    parser.add_argument('--days', '-d', type=int, default=7, 
                       help='Number of days to look back for analysis (default: 7)')
    parser.add_argument('--project', '-p', type=str, required=True,
                       help='JIRA project key(s) to analyze - single project or comma-separated list (e.g., "PROJ1" or "PROJ1,PROJ2,PROJ3")')
    parser.add_argument('--components', '-c', type=str, default=None,
                       help='Optional comma-separated components to filter by, in same order as projects (e.g., "Infrastructure,Migration" for projects "KFLUXINFRA,KFLUXMIG"). If not specified, will auto-map from project names using environment variables.')
    parser.add_argument('--main-project', '-m', type=str, default=None,
                       help='Optional main project for additional bug fetching (overrides MAIN_PROJECT env var)')
    
    args = parser.parse_args()
    
    # Parse projects - handle both single and comma-separated
    if ',' in args.project:
        projects = [p.strip() for p in args.project.split(',') if p.strip()]
    else:
        projects = [args.project.strip()]
    
    # Handle components - either from CLI or auto-mapped from projects
    if args.components:
        components = args.components
        # Show positional mapping for clarity
        components_list = [c.strip() for c in components.split(',') if c.strip()]
        
        # Warn if mismatch in counts
        if len(components_list) != len(projects):
            if len(components_list) < len(projects):
                print(f"⚠️  Warning: {len(projects)} projects but only {len(components_list)} components. Extra projects will use the last component.")
            else:
                print(f"⚠️  Warning: {len(components_list)} components but only {len(projects)} projects. Extra components will be ignored.")
        
        print(f"📋 Positional component mapping:")
        for i, project in enumerate(projects):
            if i < len(components_list):
                component = components_list[i]
            else:
                component = components_list[-1] if components_list else project
            print(f"   🔗 {project} → {component} component")
    else:
        # Auto-map components from project names
        mapped_components = []
        print(f"📋 Auto-mapping components from project names:")
        for project in projects:
            component = get_component_for_project(project)
            mapped_components.append(component)
            print(f"   🔗 {project} → {component} component")
        components = ','.join(mapped_components)
    
    # Handle main project - CLI overrides env var
    if args.main_project:
        print(f"🎯 Using main project from CLI: {args.main_project}")
    
    # Determine if components were explicitly provided
    components_provided = args.components is not None
    
    main(analysis_period_days=args.days, projects=projects, components=components, components_provided=components_provided, main_project_override=args.main_project)
