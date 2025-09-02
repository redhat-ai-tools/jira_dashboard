#!/usr/bin/env python3
"""
Full Epic Activity Analysis
Finds epics where connected issues were updated in the configurable period
Implements the complete strategy from the previous analysis
Now includes comprehensive epic content analysis and summary generation
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
    extract_json_from_result,
    post_process_summary_timestamps
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
    """Main analysis function
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 14)
        projects (list): List of JIRA project keys to analyze (required)
        components (str): Optional comma-separated components to filter by (e.g., 'component-x,component-y')
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    print(f"🎯 Multi-Project Epic Connected Issues Analysis (Last {analysis_period_days} Days)")
    print("="*80)
    print(f"📋 This will analyze epics and their connected issues from {len(projects)} project(s): {', '.join(projects)}")
    print("🔍 Looking for epics where connected issues were updated recently")
    print("📝 Will generate comprehensive summaries for active epics")
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
    """Analyze epic activity for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
        components (str): Optional comma-separated components to filter by
    """
    print(f"🎯 {project} Epic Connected Issues Analysis")
    print(f"📋 Analyzing all {project} epics and their connected issues")
    print("🔍 Looking for epics where connected issues were updated recently")
    print("📝 Will generate comprehensive summaries for active epics")
    
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
            
            # Format components parameter for task templates
            components_param = f"\n- components='{components}'" if components else ""
            
            # Task 1: Get project epics (both in progress and closed)
            print(f"📡 Phase 1: Fetching all {project} epics...")
            
            # Fetch in progress epics (status='10018')
            print(f"   📋 Fetching in progress epics (status='10018')...")
            get_epics_in_progress_task = create_task_from_config("get_epics_task", tasks_config['tasks']['get_epics_task'], agents, project=project, project_lower=project.lower(), components_param=components_param, status='10018', status_name='in_progress')
            
            # Fetch closed epics (status='6')
            print(f"   📋 Fetching closed epics (status='6')...")
            get_epics_closed_task = create_task_from_config("get_epics_task", tasks_config['tasks']['get_epics_task'], agents, project=project, project_lower=project.lower(), components_param=components_param, status='6', status_name='closed')
            
            # Create crew for epic discovery
            crew = Crew(
                agents=[agents['comprehensive_epic_analyst'], agents['comprehensive_epic_analyst']],
                tasks=[get_epics_in_progress_task, get_epics_closed_task],
                verbose=True
            )
            
            result = crew.kickoff()
            
            # Debug: Print raw result
            print(f"🐛 DEBUG: Raw crew result type: {type(result)}")
            print(f"🐛 DEBUG: Raw crew result: {result}")
            print(f"🐛 DEBUG: Result has tasks_output: {hasattr(result, 'tasks_output')}")
            if hasattr(result, 'tasks_output'):
                print(f"🐛 DEBUG: tasks_output length: {len(result.tasks_output)}")
                if len(result.tasks_output) >= 1:
                    print(f"🐛 DEBUG: First task output type: {type(result.tasks_output[0])}")
                    print(f"🐛 DEBUG: First task output: {result.tasks_output[0]}")
            
            # Initialize epic variables
            in_progress_epics = []
            closed_epics = []
            epics = []
            
            # Extract epics data from both tasks (in progress and closed)
            if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 2:
                # Extract in progress epics (first task)
                in_progress_result = result.tasks_output[0]
                in_progress_data = extract_json_from_result(in_progress_result)
                if in_progress_data and 'issues' in in_progress_data:
                    in_progress_epics = in_progress_data['issues']
                    # Mark as in progress
                    for epic in in_progress_epics:
                        epic['epic_status_type'] = 'in_progress'
                print(f"✅ Found {len(in_progress_epics)} {project} in progress epics")
                
                # Extract closed epics (second task)
                closed_result = result.tasks_output[1]
                closed_data = extract_json_from_result(closed_result)
                if closed_data and 'issues' in closed_data:
                    closed_epics = closed_data['issues']
                    # Mark as closed
                    for epic in closed_epics:
                        epic['epic_status_type'] = 'closed'
                print(f"✅ Found {len(closed_epics)} {project} closed epics")
                
                # Combine both sets of epics
                epics = in_progress_epics + closed_epics
                print(f"✅ Total {len(epics)} {project} epics (in progress: {len(in_progress_epics)}, closed: {len(closed_epics)})")
                
                if epics:
                    
                    # Phase 2: Analyze each epic's connected issues
                    print("\n📡 Phase 2: Analyzing connected issues for each epic...")
                    print("="*80)
                    
                    active_epics = []
                    cutoff_date = datetime.now() - timedelta(days=analysis_period_days)
                    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    print(f"🕒 Cutoff date: {cutoff_str} ({analysis_period_days} days ago)")
                    print("="*80)
                    
                    for i, epic in enumerate(epics, 1):
                        epic_key = epic.get('key', 'N/A')
                        epic_summary = epic.get('summary', 'No summary')
                        epic_updated = epic.get('updated', '')
                        
                        print(f"\n{i:2d}/{len(epics)} 🔍 Analyzing {epic_key}")
                        print(f"         📝 {epic_summary[:60]}{'...' if len(epic_summary) > 60 else ''}")
                        
                        # Get links for this epic
                        try:
                            links_task = create_task_from_config(
                                "epic_links_task", 
                                tasks_config['tasks']['templates']['epic_links_task'], 
                                agents,
                                epic_key=epic_key
                            )
                            
                            links_crew = Crew(
                                agents=[agents['comprehensive_epic_analyst']],
                                tasks=[links_task],
                                verbose=True
                            )
                            
                            links_result = links_crew.kickoff()
                            
                            print(f"         🐛 DEBUG: Links result type: {type(links_result)}")
                            print(f"         🐛 DEBUG: Links result: {links_result}")
                            
                            if hasattr(links_result, 'tasks_output') and len(links_result.tasks_output) >= 1:
                                print(f"         🐛 DEBUG: Links task output: {links_result.tasks_output[0]}")
                                links_data = extract_json_from_result(links_result.tasks_output[0])
                                print(f"         🐛 DEBUG: Extracted links_data: {links_data}")
                                
                                if links_data and 'links' in links_data:
                                    links = links_data['links']
                                    
                                    # Filter for child issues (outward relationships)
                                    child_issues = []
                                    for link in links:
                                        if link.get('relationship') == 'outward':
                                            child_key = link.get('related_issue_key')
                                            child_summary = link.get('related_issue_summary', 'No summary')
                                            link_type = link.get('link_type', 'Unknown')
                                            
                                            if child_key:
                                                child_issues.append({
                                                    'key': child_key,
                                                    'summary': child_summary,
                                                    'link_type': link_type
                                                })
                                    
                                    print(f"         🔗 Found {len(child_issues)} connected issues")
                                    
                                    if child_issues:
                                        recently_updated_children = []
                                        
                                        # Collect all child keys for batch processing
                                        child_keys = [child['key'] for child in child_issues]
                                        print(f"         🚀 Batch checking {len(child_keys)} child issues for recent updates...")
                                        
                                        try:
                                            # Use batch task to get all child details at once
                                            batch_child_task = create_task_from_config(
                                                "batch_child_details_task", 
                                                tasks_config['tasks']['templates']['batch_child_details_task'], 
                                                agents,
                                                child_keys=child_keys
                                            )
                                            
                                            batch_child_crew = Crew(
                                                agents=[agents['comprehensive_epic_analyst']],
                                                tasks=[batch_child_task],
                                                verbose=True
                                            )
                                            
                                            batch_child_result = batch_child_crew.kickoff()
                                            all_child_details = extract_json_from_result(batch_child_result.tasks_output[0])
                                            
                                            print(f"         ✅ Batch check completed! Processing results...")
                                            
                                            # Process batch results to find recently updated children
                                            no_data_count = 0
                                            for j, child in enumerate(child_issues):
                                                child_key = child['key']
                                                print(f"         📋 {j+1:2d}/{len(child_issues)} Checking {child_key}...", end="")
                                                
                                                # Get the details from batch result
                                                child_data = None
                                                if all_child_details and 'found_issues' in all_child_details:
                                                    child_data = all_child_details['found_issues'].get(child_key)
                                                
                                                if child_data:
                                                    child_updated = child_data.get('updated', '')
                                                    is_recent = is_timestamp_within_days(child_updated, analysis_period_days)
                                                    
                                                    if is_recent:
                                                        recently_updated_children.append({
                                                            'key': child_key,
                                                            'summary': child['summary'],
                                                            'link_type': child['link_type'],
                                                            'updated': child_updated,
                                                            'updated_formatted': format_timestamp(child_updated)
                                                        })
                                                        print(" ✅ Recently updated!")
                                                    else:
                                                        print(" ⏳ Not recent")
                                                else:
                                                    print(" ❌ No data")
                                                    no_data_count += 1
                                            
                                            # DEBUG: Only show detailed debugging if most/all issues returned no data
                                            if no_data_count == len(child_issues) and len(child_issues) > 0:
                                                print(f"         🐛 DEBUG: All {len(child_issues)} issues returned no data - investigating...")
                                                print(f"         🐛 DEBUG: Requested keys: {child_keys}")
                                                print(f"         🐛 DEBUG: Raw batch result type: {type(batch_child_result.tasks_output[0])}")
                                                raw_result = str(batch_child_result.tasks_output[0])
                                                print(f"         🐛 DEBUG: Raw batch result (first 500 chars): {raw_result[:500]}...")
                                                print(f"         🐛 DEBUG: Parsed result type: {type(all_child_details)}")
                                                print(f"         🐛 DEBUG: Parsed result keys: {list(all_child_details.keys()) if isinstance(all_child_details, dict) else 'Not a dict'}")
                                                if isinstance(all_child_details, dict) and 'found_issues' in all_child_details:
                                                    found_keys = list(all_child_details['found_issues'].keys())
                                                    print(f"         🐛 DEBUG: Found {len(found_keys)} issues in batch result: {found_keys}")
                                                    if 'not_found' in all_child_details:
                                                        print(f"         🐛 DEBUG: Not found issues: {all_child_details['not_found']}")
                                                else:
                                                    print(f"         🐛 DEBUG: No 'found_issues' key in batch result")
                                                    print(f"         🐛 DEBUG: Full parsed result: {str(all_child_details)[:800]}...")
                                            elif no_data_count > len(child_issues) // 2:
                                                print(f"         🐛 DEBUG: {no_data_count}/{len(child_issues)} issues returned no data - this may indicate a problem")
                                                    
                                        except Exception as e:
                                            print(f"         ❌ Batch check failed: {str(e)}")
                                            print("         🔄 Falling back to individual calls...")
                                            
                                            # Fallback to individual calls if batch fails
                                            for j, child in enumerate(child_issues):
                                                child_key = child['key']
                                                print(f"         📋 {j+1:2d}/{len(child_issues)} Checking {child_key} (fallback)...", end="")
                                                
                                                # Get child issue details
                                                try:
                                                    child_details_task = create_task_from_config(
                                                        "child_issue_details_task", 
                                                        tasks_config['tasks']['templates']['child_issue_details_task'], 
                                                        agents,
                                                        child_key=child_key
                                                    )
                                                    
                                                    child_crew = Crew(
                                                        agents=[agents['comprehensive_epic_analyst']],
                                                        tasks=[child_details_task],
                                                        verbose=True
                                                    )
                                                    
                                                    child_result = child_crew.kickoff()
                                                    
                                                    if hasattr(child_result, 'tasks_output') and len(child_result.tasks_output) >= 1:
                                                        child_data = extract_json_from_result(child_result.tasks_output[0])
                                                        
                                                        if child_data:
                                                            child_updated = child_data.get('updated', '')
                                                            is_recent = is_timestamp_within_days(child_updated, analysis_period_days)
                                                            
                                                            if is_recent:
                                                                recently_updated_children.append({
                                                                    'key': child_key,
                                                                    'summary': child['summary'],
                                                                    'link_type': child['link_type'],
                                                                    'updated': child_updated,
                                                                    'updated_formatted': format_timestamp(child_updated)
                                                                })
                                                                print(" ✅ Recently updated!")
                                                            else:
                                                                print(" ⏳ Not recent")
                                                        else:
                                                            print(" ❌ No data")
                                                    else:
                                                        print(" ❌ Failed")
                                                        
                                                except Exception as e:
                                                    print(f" ❌ Error: {str(e)[:30]}...")
                                        
                                        # If any children were recently updated, add this epic to active list
                                        if recently_updated_children:
                                            active_epics.append({
                                                'key': epic_key,
                                                'summary': epic_summary,
                                                'epic_status_type': epic.get('epic_status_type', 'unknown'),
                                                'epic_updated': epic_updated,
                                                'epic_updated_formatted': format_timestamp(epic_updated),
                                                'total_connected_issues': len(child_issues),
                                                'recently_updated_children': recently_updated_children,
                                                'recent_children_count': len(recently_updated_children)
                                            })
                                            
                                            print(f"         🎯 ACTIVE EPIC: {len(recently_updated_children)} recent updates found!")
                                        else:
                                            print(f"         💤 No recent child updates")
                                    else:
                                        print(f"         💭 No connected issues found")
                                else:
                                    print(f"         ❌ Could not get links data")
                                    print(f"         🐛 DEBUG: links_data type: {type(links_data)}")
                                    print(f"         🐛 DEBUG: links_data content: {links_data}")
                                    print(f"         🐛 DEBUG: Raw links result: {links_result.tasks_output[0] if hasattr(links_result, 'tasks_output') and links_result.tasks_output else 'No task output'}")
                            else:
                                print(f"         ❌ Could not get links")
                                
                        except Exception as e:
                            print(f"         ❌ Error getting links: {str(e)[:50]}...")
                    
                    # Phase 3: Generate summaries for recently updated connected issues
                    if active_epics:
                        print(f"\n" + "="*80)
                        print("📊 Phase 3: Analyzing Recently Updated Connected Issues")
                        print("="*80)
                        
                        epic_summaries = []
                        
                        for i, epic in enumerate(active_epics, 1):
                            epic_key = epic['key']
                            print(f"\n📝 {i:2d}/{len(active_epics)} Analyzing recently updated issues for {epic_key}...")
                            
                            issue_summaries = []
                            
                            # Batch analyze recently updated connected issues
                            child_keys_for_analysis = [child['key'] for child in epic['recently_updated_children']]
                            print(f"     🚀 Batch analyzing {len(child_keys_for_analysis)} recently updated issues...")
                            
                            try:
                                # Use batch task to get all issue details at once for content analysis
                                batch_analysis_task = create_task_from_config(
                                    "batch_item_details_task",  # Reuse the batch item details task
                                    tasks_config['tasks']['templates']['batch_item_details_task'],
                                    agents,
                                    item_keys=child_keys_for_analysis,
                                    fetcher_agent='connected_issues_analyzer'
                                )
                                
                                batch_analysis_crew = Crew(
                                    agents=[agents['connected_issues_analyzer']],
                                    tasks=[batch_analysis_task],
                                    verbose=True
                                )
                                
                                batch_analysis_result = batch_analysis_crew.kickoff()
                                all_issue_details_for_analysis = extract_json_from_result(batch_analysis_result.tasks_output[0])
                                
                                print(f"     ✅ Batch details fetch completed! Processing individual analyses...")
                                
                                # Now process each issue individually for content analysis
                                analysis_no_data_count = 0
                                for j, child in enumerate(epic['recently_updated_children'], 1):
                                    child_key = child['key']
                                    print(f"     🔍 {j:2d}/{len(epic['recently_updated_children'])} Analyzing {child_key}...", end="")
                                    
                                    try:
                                        # Get the detailed issue information from batch result
                                        issue_details = None
                                        if all_issue_details_for_analysis and 'found_issues' in all_issue_details_for_analysis:
                                            issue_details = all_issue_details_for_analysis['found_issues'].get(child_key)
                                        
                                        if issue_details:
                                            # Create analysis based on the detailed information
                                            # Use enhanced inline analysis with full information
                                            issue_summary = f"Issue {child_key} ({child['link_type']}) was recently updated. "
                                            
                                            # Add key details from the issue
                                            if issue_details.get('summary'):
                                                issue_summary += f"Summary: {issue_details['summary']}. "
                                            if issue_details.get('status'):
                                                issue_summary += f"Status: {issue_details['status']}. "
                                            if issue_details.get('description'):
                                                # Include full description instead of truncating
                                                desc = issue_details['description']
                                                # Only truncate if extremely long (>1000 chars)
                                                if len(desc) > 1000:
                                                    desc = desc[:1000] + "..."
                                                issue_summary += f"Description: {desc}. " if desc.strip() else ""
                                            
                                            # Add additional context if available
                                            if issue_details.get('priority'):
                                                issue_summary += f"Priority: {issue_details['priority']}. "
                                            if issue_details.get('resolution'):
                                                issue_summary += f"Resolution: {issue_details['resolution']}. "
                                            
                                            # Add comments for recent activity (IMPORTANT!)
                                            if issue_details.get('comments'):
                                                comments = issue_details.get('comments', [])
                                                if comments:
                                                    issue_summary += "Recent comments: "
                                                    # Include the most recent comments (last 3)
                                                    recent_comments = comments[-3:] if len(comments) > 3 else comments
                                                    for comment in recent_comments:
                                                        comment_body = comment.get('body', '').strip()
                                                        if comment_body:
                                                            # Truncate very long comments
                                                            if len(comment_body) > 500:
                                                                comment_body = comment_body[:500] + "..."
                                                            issue_summary += f"[{comment_body}] "
                                                    issue_summary += ". "
                                            
                                            # Post-process to format any raw timestamps
                                            issue_summary_formatted = post_process_summary_timestamps(issue_summary)
                                            
                                            issue_summaries.append({
                                                'issue_key': child_key,
                                                'issue_title': child['summary'],
                                                'link_type': child['link_type'],
                                                'updated_formatted': child['updated_formatted'],
                                                'detailed_summary': issue_summary_formatted
                                            })
                                            
                                            print(f" ✅ Done ({len(issue_summary)} chars)")
                                        else:
                                            print(f" ❌ No details")
                                            analysis_no_data_count += 1
                                            
                                    except Exception as e:
                                        print(f" ❌ Error: {str(e)[:30]}...")
                                        analysis_no_data_count += 1
                                
                                # DEBUG: Only show detailed debugging if most/all analysis requests returned no data
                                if analysis_no_data_count == len(child_keys_for_analysis) and len(child_keys_for_analysis) > 0:
                                    print(f"     🐛 DEBUG: All {len(child_keys_for_analysis)} analysis requests returned no data - investigating...")
                                    print(f"     🐛 DEBUG: Requested analysis keys: {child_keys_for_analysis}")
                                    print(f"     🐛 DEBUG: Raw analysis result (first 500 chars): {str(batch_analysis_result.tasks_output[0])[:500]}...")
                                    print(f"     🐛 DEBUG: Parsed analysis result type: {type(all_issue_details_for_analysis)}")
                                    if isinstance(all_issue_details_for_analysis, dict) and 'found_issues' in all_issue_details_for_analysis:
                                        found_keys = list(all_issue_details_for_analysis['found_issues'].keys())
                                        print(f"     🐛 DEBUG: Found {len(found_keys)} issues for analysis: {found_keys}")
                                        if 'not_found' in all_issue_details_for_analysis:
                                            print(f"     🐛 DEBUG: Not found for analysis: {all_issue_details_for_analysis['not_found']}")
                                    else:
                                        print(f"     🐛 DEBUG: No 'found_issues' key in analysis result")
                                        print(f"     🐛 DEBUG: Full analysis result: {str(all_issue_details_for_analysis)[:800]}...")
                                elif analysis_no_data_count > len(child_keys_for_analysis) // 2:
                                    print(f"     🐛 DEBUG: {analysis_no_data_count}/{len(child_keys_for_analysis)} analysis requests returned no data - this may indicate a problem")
                                        
                            except Exception as e:
                                print(f"     ❌ Batch analysis failed: {str(e)}")
                                print("     🔄 Falling back to individual calls...")
                                
                                # Fallback to individual calls if batch fails
                                for j, child in enumerate(epic['recently_updated_children'], 1):
                                    child_key = child['key']
                                    print(f"     🔍 {j:2d}/{len(epic['recently_updated_children'])} Analyzing {child_key} (fallback)...", end="")
                                    
                                    try:
                                        # Get detailed issue information and create summary
                                        issue_analysis_task = create_task_from_config(
                                            "issue_content_analysis_task",
                                            tasks_config['tasks']['templates']['issue_content_analysis_task'],
                                            agents,
                                            child_key=child_key,
                                            updated_formatted=child['updated_formatted']
                                        )
                                        
                                        issue_crew = Crew(
                                            agents=[agents['connected_issues_analyzer']],
                                            tasks=[issue_analysis_task],
                                            verbose=True
                                        )
                                        
                                        issue_result = issue_crew.kickoff()
                                        
                                        if hasattr(issue_result, 'tasks_output') and len(issue_result.tasks_output) >= 1:
                                            issue_summary = str(issue_result.tasks_output[0])
                                            
                                            # Post-process to format any raw timestamps
                                            issue_summary_formatted = post_process_summary_timestamps(issue_summary)
                                            
                                            issue_summaries.append({
                                                'issue_key': child_key,
                                                'issue_title': child['summary'],
                                                'link_type': child['link_type'],
                                                'updated_formatted': child['updated_formatted'],
                                                'detailed_summary': issue_summary_formatted
                                            })
                                            
                                            print(f" ✅ Done ({len(issue_summary)} chars)")
                                        else:
                                            print(f" ❌ Failed")
                                            
                                    except Exception as e:
                                        print(f" ❌ Error: {str(e)[:30]}...")
                            
                            # Now create epic-level summary based on the issue summaries
                            if issue_summaries:
                                print(f"     📊 Creating epic summary based on {len(issue_summaries)} issue summaries...")
                                
                                try:
                                    # Prepare issue summaries text for epic analysis with additional timestamp formatting
                                    issues_text = ""
                                    for issue_sum in issue_summaries:
                                        issues_text += f"\n--- {issue_sum['issue_key']}: {issue_sum['issue_title']} ---\n"
                                        issues_text += f"Link Type: {issue_sum['link_type']}\n"
                                        issues_text += f"Last Updated: {issue_sum['updated_formatted']}\n"
                                        
                                        # Note: Dates are pre-formatted, agent should not process timestamps
                                        issues_text += f"Note: All necessary dates are already properly formatted. Do not reference specific dates in your summary.\n"
                                        issues_text += f"Summary: {issue_sum['detailed_summary']}\n"
                                        issues_text += "-" * 50 + "\n"
                                    
                                    epic_synthesis_task = create_task_from_config(
                                        "epic_synthesis_task",
                                        tasks_config['tasks']['templates']['epic_synthesis_task'],
                                        agents,
                                        epic_key=epic_key,
                                        epic_summary=epic['summary'],
                                        issues_text=issues_text
                                    )
                                    
                                    epic_crew = Crew(
                                        agents=[agents['connected_issues_analyzer']],
                                        tasks=[epic_synthesis_task],
                                        verbose=True
                                    )
                                    
                                    epic_result = epic_crew.kickoff()
                                    
                                    if hasattr(epic_result, 'tasks_output') and len(epic_result.tasks_output) >= 1:
                                        epic_summary_content = str(epic_result.tasks_output[0])
                                        
                                        # Post-process to format any raw timestamps in epic summary
                                        epic_summary_formatted = post_process_summary_timestamps(epic_summary_content)
                                        
                                        epic_summaries.append({
                                            'epic_key': epic_key,
                                            'epic_summary': epic['summary'],
                                            'epic_status_type': epic.get('epic_status_type', 'unknown'),
                                            'recent_children_count': epic['recent_children_count'],
                                            'recently_updated_issues': issue_summaries,
                                            'epic_level_summary': epic_summary_formatted,
                                            'analysis_timestamp': datetime.now().isoformat()
                                        })
                                        
                                        print(f"     ✅ Epic summary completed ({len(epic_summary_content)} chars)")
                                    else:
                                        print(f"     ❌ Failed to create epic summary")
                                        
                                except Exception as e:
                                    print(f"     ❌ Error creating epic summary: {str(e)[:50]}...")
                        
                        # Save summaries to text file
                        if epic_summaries:
                            print(f"\n📄 Saving epic summaries to file...")
                            
                            # Separate epics by status
                            in_progress_summaries = [s for s in epic_summaries if s.get('epic_status_type') == 'in_progress']
                            closed_summaries = [s for s in epic_summaries if s.get('epic_status_type') == 'closed']
                            
                            # Use project-specific filename
                            epic_summaries_file = f'{project.lower()}_recently_updated_epics_summary.txt'
                            with open(epic_summaries_file, 'w', encoding='utf-8') as f:
                                f.write(f"{project} EPICS WITH RECENTLY UPDATED CONNECTED ISSUES\n")
                                f.write("=" * 80 + "\n")
                                f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Analysis Period: Last {analysis_period_days} days (since {cutoff_str})\n")
                                f.write(f"Total Active Epics Found: {len(epic_summaries)}\n")
                                f.write(f"  - In Progress Epics: {len(in_progress_summaries)}\n")
                                f.write(f"  - Closed Epics: {len(closed_summaries)}\n")
                                f.write("=" * 80 + "\n\n")
                                
                                # Write IN PROGRESS EPICS section
                                if in_progress_summaries:
                                    f.write("🔄 IN PROGRESS EPICS WITH RECENT ACTIVITY\n")
                                    f.write("=" * 60 + "\n\n")
                                    
                                    for i, summary in enumerate(in_progress_summaries, 1):
                                        f.write(f"{i}. EPIC: {summary['epic_key']} [IN PROGRESS]\n")
                                        f.write("-" * 60 + "\n")
                                        f.write(f"Epic Title: {summary['epic_summary']}\n")
                                        f.write(f"Recently Updated Connected Issues: {summary['recent_children_count']}\n")
                                        f.write(f"Analysis Date: {summary['analysis_timestamp']}\n\n")
                                        
                                        # Write individual issue summaries
                                        f.write("RECENTLY UPDATED CONNECTED ISSUES:\n")
                                        f.write("-" * 40 + "\n")
                                        for j, issue in enumerate(summary['recently_updated_issues'], 1):
                                            f.write(f"\n{j}. ISSUE: {issue['issue_key']} ({issue['link_type']})\n")
                                            f.write(f"   Title: {issue['issue_title']}\n")
                                            f.write(f"   Last Updated: {issue['updated_formatted']}\n")
                                            f.write(f"   Summary:\n")
                                            f.write(f"   {issue['detailed_summary']}\n")
                                            f.write("-" * 30 + "\n")
                                        
                                        # Write epic-level summary
                                        f.write("\nEPIC-LEVEL SUMMARY (Based on Recently Updated Issues):\n")
                                        f.write("-" * 40 + "\n")
                                        f.write(summary['epic_level_summary'])
                                        f.write("\n\n" + "=" * 80 + "\n\n")
                                
                                # Write CLOSED EPICS section
                                if closed_summaries:
                                    f.write("✅ CLOSED EPICS WITH RECENT ACTIVITY\n")
                                    f.write("=" * 60 + "\n\n")
                                    
                                    for i, summary in enumerate(closed_summaries, 1):
                                        f.write(f"{i}. EPIC: {summary['epic_key']} [CLOSED]\n")
                                        f.write("-" * 60 + "\n")
                                        f.write(f"Epic Title: {summary['epic_summary']}\n")
                                        f.write(f"Recently Updated Connected Issues: {summary['recent_children_count']}\n")
                                        f.write(f"Analysis Date: {summary['analysis_timestamp']}\n\n")
                                        
                                        # Write individual issue summaries
                                        f.write("RECENTLY UPDATED CONNECTED ISSUES:\n")
                                        f.write("-" * 40 + "\n")
                                        for j, issue in enumerate(summary['recently_updated_issues'], 1):
                                            f.write(f"\n{j}. ISSUE: {issue['issue_key']} ({issue['link_type']})\n")
                                            f.write(f"   Title: {issue['issue_title']}\n")
                                            f.write(f"   Last Updated: {issue['updated_formatted']}\n")
                                            f.write(f"   Summary:\n")
                                            f.write(f"   {issue['detailed_summary']}\n")
                                            f.write("-" * 30 + "\n")
                                        
                                        # Write epic-level summary
                                        f.write("\nEPIC-LEVEL SUMMARY (Based on Recently Updated Issues):\n")
                                        f.write("-" * 40 + "\n")
                                        f.write(summary['epic_level_summary'])
                                        f.write("\n\n" + "=" * 80 + "\n\n")
                            
                            print(f"✅ Epic summaries saved to: {epic_summaries_file}")
                    
                    # Phase 4: Generate comprehensive report
                    print(f"\n" + "="*80)
                    print("📊 COMPREHENSIVE RESULTS")
                    print("="*80)
                    
                    if active_epics:
                        # Separate active epics by status
                        active_in_progress = [epic for epic in active_epics if epic.get('epic_status_type') == 'in_progress']
                        active_closed = [epic for epic in active_epics if epic.get('epic_status_type') == 'closed']
                        
                        print(f"🎯 Found {len(active_epics)} epics with recently updated connected issues:")
                        print(f"   🔄 In Progress: {len(active_in_progress)}")
                        print(f"   ✅ Closed: {len(active_closed)}")
                        
                        # Display IN PROGRESS epics
                        if active_in_progress:
                            print(f"\n🔄 IN PROGRESS EPICS ({len(active_in_progress)}):")
                            for i, epic in enumerate(active_in_progress, 1):
                                print(f"\n{i:2d}. 📋 {epic['key']}: {epic['summary']}")
                                print(f"     📅 Epic updated: {epic['epic_updated_formatted']}")
                                print(f"     🔗 Total connected: {epic['total_connected_issues']}")
                                print(f"     ⚡ Recent updates: {epic['recent_children_count']}")
                                
                                print(f"     📝 Recently updated connected issues:")
                                for j, child in enumerate(epic['recently_updated_children'], 1):
                                    print(f"       {j}. {child['key']} ({child['link_type']})")
                                    print(f"          📅 Updated: {child['updated_formatted']}")
                                    print(f"          📝 {child['summary'][:80]}{'...' if len(child['summary']) > 80 else ''}")
                        
                        # Display CLOSED epics
                        if active_closed:
                            print(f"\n✅ CLOSED EPICS ({len(active_closed)}):")
                            for i, epic in enumerate(active_closed, 1):
                                print(f"\n{i:2d}. 📋 {epic['key']}: {epic['summary']}")
                                print(f"     📅 Epic updated: {epic['epic_updated_formatted']}")
                                print(f"     🔗 Total connected: {epic['total_connected_issues']}")
                                print(f"     ⚡ Recent updates: {epic['recent_children_count']}")
                                
                                print(f"     📝 Recently updated connected issues:")
                                for j, child in enumerate(epic['recently_updated_children'], 1):
                                    print(f"       {j}. {child['key']} ({child['link_type']})")
                                    print(f"          📅 Updated: {child['updated_formatted']}")
                                    print(f"          📝 {child['summary'][:80]}{'...' if len(child['summary']) > 80 else ''}")
                    else:
                        print("💡 No epics found with recently updated connected issues")
                        print("📝 Note: All epics were checked for connected issue activity")
                    
                    # Save comprehensive results
                    # Separate counts by status
                    active_in_progress = [epic for epic in active_epics if epic.get('epic_status_type') == 'in_progress']
                    active_closed = [epic for epic in active_epics if epic.get('epic_status_type') == 'closed']
                    
                    output_data = {
                        'analysis_date': datetime.now().isoformat(),
                        'cutoff_date': cutoff_date.isoformat(),
                        'cutoff_date_formatted': cutoff_str,
                        'analysis_scope': f'Connected issues for all {project} epics (both in progress and closed)',
                        'total_epics_analyzed': len(epics),
                        'total_in_progress_epics': len(in_progress_epics),
                        'total_closed_epics': len(closed_epics),
                        'active_epics_count': len(active_epics),
                        'active_in_progress_count': len(active_in_progress),
                        'active_closed_count': len(active_closed),
                        'active_epics': active_epics,
                        'active_in_progress_epics': active_in_progress,
                        'active_closed_epics': active_closed,
                        'epic_summaries_generated': len(epic_summaries) if 'epic_summaries' in locals() else 0,
                        'summary': {
                            'strategy': 'Full connected issue analysis with content summaries for both in progress and closed epics',
                            'criteria': f'Epics where connected issues updated in last {analysis_period_days} days',
                            'total_recent_children': sum(epic['recent_children_count'] for epic in active_epics),
                            'in_progress_recent_children': sum(epic['recent_children_count'] for epic in active_in_progress),
                            'closed_recent_children': sum(epic['recent_children_count'] for epic in active_closed)
                        }
                    }
                    
                    with open(f'{project.lower()}_full_epic_activity_analysis.json', 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, indent=2, ensure_ascii=False)
                    
                    print(f"\n💾 Comprehensive analysis saved to: {project.lower()}_full_epic_activity_analysis.json")
                    
                    # Summary statistics
                    total_recent_children = sum(epic['recent_children_count'] for epic in active_epics)
                    active_in_progress = [epic for epic in active_epics if epic.get('epic_status_type') == 'in_progress']
                    active_closed = [epic for epic in active_epics if epic.get('epic_status_type') == 'closed']
                    
                    print(f"\n📊 SUMMARY STATISTICS:")
                    print(f"   📋 Total {project} epics analyzed: {len(epics)}")
                    print(f"     🔄 In Progress epics: {len(in_progress_epics)}")
                    print(f"     ✅ Closed epics: {len(closed_epics)}")
                    print(f"   🎯 Epics with recent connected updates: {len(active_epics)}")
                    print(f"     🔄 Active In Progress epics: {len(active_in_progress)}")
                    print(f"     ✅ Active Closed epics: {len(active_closed)}")
                    print(f"   ⚡ Total recently updated connected issues: {total_recent_children}")
                    if active_in_progress:
                        in_progress_children = sum(epic['recent_children_count'] for epic in active_in_progress)
                        print(f"     🔄 In Progress epic issues: {in_progress_children}")
                    if active_closed:
                        closed_children = sum(epic['recent_children_count'] for epic in active_closed)
                        print(f"     ✅ Closed epic issues: {closed_children}")
                    print(f"   📝 Epic content summaries generated: {len(epic_summaries) if 'epic_summaries' in locals() else 0}")
                    print(f"   📅 Analysis period: Last {analysis_period_days} days (since {cutoff_str})")
                    
                else:
                    print("❌ Could not extract epics data from both tasks")
                    print(f"🐛 DEBUG: Expected 2 tasks (in progress + closed), got {len(result.tasks_output) if hasattr(result, 'tasks_output') else 0}")
            else:
                print("❌ Could not get epics")
                print(f"🐛 DEBUG: Result structure issue - expected 2 tasks (in progress + closed) but got {len(result.tasks_output) if hasattr(result, 'tasks_output') else 0}")
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise  # Re-raise to be handled by the multi-project loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze epic activity based on connected issues for one or more projects')
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
