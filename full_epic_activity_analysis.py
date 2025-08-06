#!/usr/bin/env python3
"""
Full KONFLUX Epic Activity Analysis
Finds epics where connected issues were updated in the last 2 weeks
Implements the complete strategy from the previous analysis
Now includes comprehensive epic content analysis and summary generation
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
    extract_json_from_result,
    post_process_summary_timestamps
)

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
    """Main analysis function"""
    print("🎯 KONFLUX Epic Connected Issues Analysis (Last 2 Weeks)")
    print("="*80)
    print("📋 This will analyze all KONFLUX epics and their connected issues")
    print("🔍 Looking for epics where connected issues were updated recently")
    print("📝 Will generate comprehensive summaries for active epics")
    print("="*80)
    
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
            
            # Task 1: Get all KONFLUX epics (we know there are 9 from previous run)
            get_epics_task = create_task_from_config("get_epics_task", tasks_config['tasks']['get_epics_task'], agents)
            
            # Create crew for epic discovery
            crew = Crew(
                agents=[agents['comprehensive_epic_analyst']],
                tasks=[get_epics_task],
                verbose=True
            )
            
            print("📡 Phase 1: Fetching all KONFLUX epics...")
            result = crew.kickoff()
            
            # Extract epics data
            if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 1:
                epics_result = result.tasks_output[0]
                epics_data = extract_json_from_result(epics_result)
                
                if epics_data and 'issues' in epics_data:
                    epics = epics_data['issues']
                    print(f"✅ Found {len(epics)} KONFLUX epics")
                    
                    # Phase 2: Analyze each epic's connected issues
                    print("\n📡 Phase 2: Analyzing connected issues for each epic...")
                    print("="*80)
                    
                    active_epics = []
                    cutoff_date = datetime.now() - timedelta(days=14)
                    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    print(f"🕒 Cutoff date: {cutoff_str} (14 days ago)")
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
                            
                            if hasattr(links_result, 'tasks_output') and len(links_result.tasks_output) >= 1:
                                links_data = extract_json_from_result(links_result.tasks_output[0])
                                
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
                                        
                                        # Check each child issue for recent updates
                                        for j, child in enumerate(child_issues):
                                            child_key = child['key']
                                            
                                            print(f"         📋 {j+1:2d}/{len(child_issues)} Checking {child_key}...", end="")
                                            
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
                                                    verbose=False
                                                )
                                                
                                                child_result = child_crew.kickoff()
                                                
                                                if hasattr(child_result, 'tasks_output') and len(child_result.tasks_output) >= 1:
                                                    child_data = extract_json_from_result(child_result.tasks_output[0])
                                                    
                                                    if child_data:
                                                        child_updated = child_data.get('updated', '')
                                                        
                                                        if is_timestamp_within_days(child_updated, 14):
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
                                                        print(f"           🐛 DEBUG: child_data type: {type(child_data)}")
                                                        print(f"           🐛 DEBUG: child_data content: {child_data}")
                                                        print(f"           🐛 DEBUG: Raw child result: {child_result.tasks_output[0] if hasattr(child_result, 'tasks_output') and child_result.tasks_output else 'No task output'}")
                                                else:
                                                    print(" ❌ Failed")
                                                    
                                            except Exception as e:
                                                print(f" ❌ Error: {str(e)[:30]}...")
                                        
                                        # If any children were recently updated, add this epic to active list
                                        if recently_updated_children:
                                            active_epics.append({
                                                'key': epic_key,
                                                'summary': epic_summary,
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
                            
                            # Analyze each recently updated connected issue
                            for j, child in enumerate(epic['recently_updated_children'], 1):
                                child_key = child['key']
                                print(f"     🔍 {j:2d}/{len(epic['recently_updated_children'])} Analyzing {child_key}...", end="")
                                
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
                                        verbose=False
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
                                        verbose=False
                                    )
                                    
                                    epic_result = epic_crew.kickoff()
                                    
                                    if hasattr(epic_result, 'tasks_output') and len(epic_result.tasks_output) >= 1:
                                        epic_summary_content = str(epic_result.tasks_output[0])
                                        
                                        # Post-process to format any raw timestamps in epic summary
                                        epic_summary_formatted = post_process_summary_timestamps(epic_summary_content)
                                        
                                        epic_summaries.append({
                                            'epic_key': epic_key,
                                            'epic_summary': epic['summary'],
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
                            
                            with open('recently_updated_epics_summary.txt', 'w', encoding='utf-8') as f:
                                f.write("KONFLUX EPICS WITH RECENTLY UPDATED CONNECTED ISSUES\n")
                                f.write("=" * 80 + "\n")
                                f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Analysis Period: Last 14 days (since {cutoff_str})\n")
                                f.write(f"Total Active Epics Found: {len(epic_summaries)}\n")
                                f.write("=" * 80 + "\n\n")
                                
                                for i, summary in enumerate(epic_summaries, 1):
                                    f.write(f"{i}. EPIC: {summary['epic_key']}\n")
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
                            
                            print(f"✅ Epic summaries saved to: recently_updated_epics_summary.txt")
                    
                    # Phase 4: Generate comprehensive report
                    print(f"\n" + "="*80)
                    print("📊 COMPREHENSIVE RESULTS")
                    print("="*80)
                    
                    if active_epics:
                        print(f"🎯 Found {len(active_epics)} epics with recently updated connected issues:")
                        
                        for i, epic in enumerate(active_epics, 1):
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
                    output_data = {
                        'analysis_date': datetime.now().isoformat(),
                        'cutoff_date': cutoff_date.isoformat(),
                        'cutoff_date_formatted': cutoff_str,
                        'analysis_scope': 'Connected issues for all KONFLUX epics',
                        'total_epics_analyzed': len(epics),
                        'active_epics_count': len(active_epics),
                        'active_epics': active_epics,
                        'epic_summaries_generated': len(epic_summaries) if 'epic_summaries' in locals() else 0,
                        'summary': {
                            'strategy': 'Full connected issue analysis with content summaries',
                            'criteria': 'Epics where connected issues updated in last 14 days',
                            'total_recent_children': sum(epic['recent_children_count'] for epic in active_epics)
                        }
                    }
                    
                    with open('konflux_full_epic_activity_analysis.json', 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, indent=2, ensure_ascii=False)
                    
                    print(f"\n💾 Comprehensive analysis saved to: konflux_full_epic_activity_analysis.json")
                    
                    # Summary statistics
                    total_recent_children = sum(epic['recent_children_count'] for epic in active_epics)
                    print(f"\n📊 SUMMARY STATISTICS:")
                    print(f"   📋 Total KONFLUX epics analyzed: {len(epics)}")
                    print(f"   🎯 Epics with recent connected updates: {len(active_epics)}")
                    print(f"   ⚡ Total recently updated connected issues: {total_recent_children}")
                    print(f"   📝 Epic content summaries generated: {len(epic_summaries) if 'epic_summaries' in locals() else 0}")
                    print(f"   📅 Analysis period: Last 14 days (since {cutoff_str})")
                    
                else:
                    print("❌ Could not extract epics data")
            else:
                print("❌ Could not get epics")
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main() 