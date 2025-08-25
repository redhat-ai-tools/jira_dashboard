#!/usr/bin/env python3
"""
Issues Executive Report Generator
Fetches and analyzes recently created issues from specified project.
Generates: {project}_executive_report.html with executive summary and recommendations.
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
    generate_html_report
)

# Configure Gemini LLM
gemini_api_key = os.getenv("GEMINI_API_KEY")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")
jira_base_url = os.getenv("JIRA_BASE_URL")

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

def main(analysis_period_days=14, projects=None, components=None):
    """Main function to generate executive report
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 14)
        projects (list): List of JIRA project keys to analyze (required)
        components (str): Optional comma-separated components to filter by (e.g., 'component-x,component-y')
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    print(f"📊 Multi-Project Executive Report Generator")
    print("="*80)
    print(f"📋 This will analyze recently created issues from {len(projects)} project(s): {', '.join(projects)}")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output files: [project]_executive_report.html for each project")
    print("="*80)
    
    # Process each project
    for i, project in enumerate(projects, 1):
        print(f"\n🔍 Processing project {i}/{len(projects)}: {project}")
        print("=" * 60)
        
        try:
            analyze_single_project(analysis_period_days, project, components)
            print(f"✅ {project} executive report completed successfully")
        except Exception as e:
            print(f"❌ Error analyzing {project}: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"⏭️  Continuing with next project...")
    
    print(f"\n🎉 Multi-project executive report generation complete! Processed {len(projects)} projects.")

def analyze_single_project(analysis_period_days, project, components=None):
    """Generate executive report for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
        components (str): Optional comma-separated components to filter by
    """
    print(f"📊 {project} Executive Report")
    print(f"📋 Analyzing recently created issues from {project} project")
    print(f"🕒 Analysis period: Last {analysis_period_days} days")
    print(f"📄 Output file: {project.lower()}_executive_report.html")
    
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
            
            # Step 1: Fetch recently created issues
            print(f"\n📡 Step 1: Fetching recently created issues from {project} (last {analysis_period_days} days)...")
            
            # Format components parameter for task templates
            components_param = f"\n- components='{components}'" if components else ""
            
            # Fetch recently created issues
            print("   🔍 Fetching recently created issues...")
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
                        print(f"   📊 Found {len(all_issues)} recently created issues")
                    else:
                        print(f"   ⚠️  No issues data or empty result")
                except (FileNotFoundError, Exception) as e:
                    print(f"   ⚠️  Could not read {issues_json_file}: {e}")
            except Exception as e:
                print(f"   ❌ Error reading issues JSON file: {e}")
            
            if not all_issues:
                print(f"   ⚠️  No issues found for analysis. Generating minimal report...")
                generate_minimal_html_report(project, analysis_period_days, components)
                return
            
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
            
            # Step 3: Calculate total issues count
            print(f"\n🧮 Step 3: Calculating total issues count...")
            total_issues_count = calculate_total_issues(detailed_issues)
            print(f"   ✅ Total issues calculated: {total_issues_count}")
            
            # Step 4: Generate executive analysis
            print(f"\n🤖 Step 4: Generating executive analysis with detailed data...")
            
            analysis_task = create_task_from_config(
                "issues_executive_analysis_task",
                tasks_config['tasks']['templates']['issues_executive_analysis_task'],
                agents,
                project=project,
                issues_data=json.dumps(detailed_issues, indent=2)
            )
            
            analysis_crew = Crew(
                agents=[agents['issues_executive_analyst']],
                tasks=[analysis_task],
                verbose=True
            )
            
            analysis_result = analysis_crew.kickoff()
            executive_summary = str(analysis_result.tasks_output[0]).strip()
            
            print(f"   ✅ Executive analysis completed ({len(executive_summary)} chars)")
            
            # Step 5: Generate HTML report
            print(f"\n📄 Step 5: Generating HTML executive report...")
            
            html_report = generate_html_report(
                project=project,
                analysis_period_days=analysis_period_days,
                components=components,
                total_issues=total_issues_count,
                issues_sample=detailed_issues,
                executive_summary=executive_summary,
                jira_base_url=jira_base_url
            )
            
            # Save HTML report
            html_filename = f'{project.lower()}_executive_report.html'
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_report)
            
            print(f"✅ Executive report saved to: {html_filename}")
            
            # Summary statistics
            print(f"\n📊 SUMMARY STATISTICS:")
            print(f"   📋 Total issues analyzed: {total_issues_count}")
            print(f"   🕒 Analysis period: Last {analysis_period_days} days")
            print(f"   🧩 Components filter: {components if components else 'None'}")
            print(f"   📄 HTML report: {html_filename}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise  # Re-raise to be handled by the multi-project loop


def generate_minimal_html_report(project, analysis_period_days, components):
    """Generate minimal HTML report when no issues found"""
    components_display = f"<strong>Components:</strong> {components}" if components else "<strong>Components:</strong> All"
    
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
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin: -30px -30px 30px -30px;
        }}
        .no-issues {{
            background: #e7f3ff;
            border: 1px solid #0066cc;
            border-radius: 8px;
            padding: 30px;
            margin: 30px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {project} Executive Issues Report</h1>
            <div>Strategic Analysis of Recently Created Issues</div>
        </div>

        <div class="no-issues">
            <h2>🎉 No Issues Found</h2>
            <p>No issues were created in the last {analysis_period_days} days matching the specified criteria.</p>
            <p>{components_display}</p>
            <p>This could indicate a stable period or that issues are being reported in different timeframes.</p>
        </div>

        <div style="margin-top: 40px; color: #666;">
            <p>Report generated by JIRA Analysis System | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Save minimal report
    html_filename = f'{project.lower()}_executive_report.html'
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Minimal executive report saved to: {html_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate executive issues report for one or more projects')
    parser.add_argument('--days', '-d', type=int, default=14, 
                       help='Number of days to look back for analysis (default: 14)')
    parser.add_argument('--project', '-p', type=str, required=True,
                       help='JIRA project key(s) to analyze - single project or comma-separated list (e.g., "PROJ1" or "PROJ1,PROJ2,PROJ3")')
    parser.add_argument('--components', '-c', type=str, default=None,
                       help='Optional comma-separated components to filter by (e.g., "component-x,component-y")')
    
    args = parser.parse_args()
    
    # Parse projects - handle both single and comma-separated
    if ',' in args.project:
        projects = [p.strip() for p in args.project.split(',') if p.strip()]
    else:
        projects = [args.project.strip()]
    
    main(analysis_period_days=args.days, projects=projects, components=args.components)
