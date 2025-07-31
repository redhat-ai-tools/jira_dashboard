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

# Configure Gemini LLM
gemini_api_key = os.getenv("GEMINI_API_KEY")

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
        "X-Snowflake-Token": "token"
    }
}

def create_agent(mcp_tools):
    """Create agent for comprehensive epic analysis"""
    return Agent(
        role="Comprehensive Epic Analyst",
        goal="Analyze KONFLUX epics and their connected issues for recent activity",
        backstory="You systematically analyze epic relationships and track recent updates across all connected issues.",
        tools=mcp_tools,
        llm=llm,
        verbose=False
    )

def create_epic_content_analyzer(mcp_tools):
    """Create specialized agent for analyzing connected issues and synthesizing epic insights"""
    return Agent(
        role="Connected Issues Analyzer and Epic Synthesizer",
        goal="Analyze recently updated connected issues and synthesize epic-level insights from their collective progress",
        backstory="""You are an expert at analyzing JIRA issues and their connections to epics. 
        You examine individual issues to understand what work was done, their purpose, and recent activity.
        Then you synthesize insights across multiple connected issues to create comprehensive epic-level 
        summaries that show overall progress, challenges, and direction. You focus on recent activity 
        and how individual issue progress contributes to the broader epic goals.
        
        CRITICAL: You NEVER mention specific dates or timestamps in your summaries. All necessary 
        dates are pre-formatted in the data provided to you. Focus on work content and progress, 
        not date details. Use only relative terms like "recently updated" if timing is relevant.""",
        tools=mcp_tools,
        llm=llm,
        verbose=False
    )

def extract_json_from_result(result_text):
    """Extract JSON data from CrewAI result, handling cases where agent adds extra text after JSON"""
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
    
    result_str = str(result_text).strip()
    
    # First try to parse the full string as JSON
    try:
        return json.loads(result_str)
    except:
        # If full string parsing fails, try to extract just the JSON part
        # This handles cases where agent adds extra text after JSON
        if result_str.startswith('{'):
            # Find the matching closing brace
            brace_count = 0
            end_pos = 0
            for i, char in enumerate(result_str):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
            if end_pos > 0:
                json_part = result_str[:end_pos]
                try:
                    return json.loads(json_part)
                except:
                    pass
        elif result_str.startswith('['):
            # Find the matching closing bracket
            bracket_count = 0
            end_pos = 0
            for i, char in enumerate(result_str):
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i + 1
                        break
            if end_pos > 0:
                json_part = result_str[:end_pos]
                try:
                    return json.loads(json_part)
                except:
                    pass
    
    # Debug: print the actual result structure to understand what we're getting
    print(f"Debug: result_text type: {type(result_text)}")
    print(f"Debug: result_text content preview: {str(result_text)[:200]}...")
    
    return None

def is_within_last_two_weeks(timestamp):
    """Check if timestamp is within the last 14 days"""
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
        
        # Check if within last 14 days
        cutoff_date = datetime.now() - timedelta(days=14)
        return dt >= cutoff_date
        
    except Exception as e:
        return False

def format_timestamp(timestamp):
    """Convert timestamp to readable format"""
    try:
        if isinstance(timestamp, str):
            timestamp_parts = timestamp.strip().split()
            if timestamp_parts:
                timestamp_str = timestamp_parts[0]
                timestamp_float = float(timestamp_str)
                dt = datetime.fromtimestamp(timestamp_float)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown"
    except:
        return "Invalid"

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
            
            agent = create_agent(mcp_tools)
            content_analyzer = create_epic_content_analyzer(mcp_tools)
            
            # Task 1: Get all KONFLUX epics (we know there are 9 from previous run)
            get_epics_task = Task(
                description="""
                Use list_jira_issues to get all KONFLUX epics:
                
                Call list_jira_issues with:
                - project='KONFLUX'
                - issue_type='16' (Epic)
                - limit=50
                - status='10018'
                
                CRITICAL: Return the complete list of epics with complete information as VALID JSON.
                Your response must be parseable JSON, not text description.
                Ensure the response contains the exact JSON structure returned by the MCP tool.
                """,
                agent=agent,
                expected_output="Valid JSON data containing KONFLUX epics - must be parseable as JSON",
                output_file="in_progress_epics.json"
            )
            
            # Create crew for epic discovery
            crew = Crew(
                agents=[agent],
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
                            links_task = Task(
                                description=f"""
                                Use get_jira_issue_links to get all connections for epic {epic_key}.
                                
                                Call get_jira_issue_links with:
                                - issue_key='{epic_key}'
                                
                                CRITICAL: Return all connected issues and their relationship information as VALID JSON.
                                Your response must be the exact JSON structure returned by the MCP tool.
                                Do not add any text description or explanation - only return parseable JSON.
                                The JSON should contain 'links' array and other fields from the MCP response.
                                """,
                                agent=agent,
                                expected_output=f"Valid parseable JSON data with all linked issues for epic {epic_key}"
                            )
                            
                            links_crew = Crew(
                                agents=[agent],
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
                                                child_details_task = Task(
                                                    description=f"""
                                                    Use get_jira_issue_details to get update information for {child_key}.
                                                    
                                                    Call get_jira_issue_details with:
                                                    - issue_key='{child_key}'
                                                    
                                                    CRITICAL: Return the issue details including the 'updated' timestamp as VALID JSON.
                                                    Your response must be the exact JSON structure returned by the MCP tool.
                                                    Do not add any text description - only return parseable JSON.
                                                    """,
                                                    agent=agent,
                                                    expected_output=f"Valid parseable JSON data containing issue details for {child_key} including update timestamp"
                                                )
                                                
                                                child_crew = Crew(
                                                    agents=[agent],
                                                    tasks=[child_details_task],
                                                    verbose=False
                                                )
                                                
                                                child_result = child_crew.kickoff()
                                                
                                                if hasattr(child_result, 'tasks_output') and len(child_result.tasks_output) >= 1:
                                                    child_data = extract_json_from_result(child_result.tasks_output[0])
                                                    
                                                    if child_data:
                                                        child_updated = child_data.get('updated', '')
                                                        
                                                        if is_within_last_two_weeks(child_updated):
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
                                    issue_analysis_task = Task(
                                        description=f"""
                                        Use get_jira_issue_details to get comprehensive information for issue {child_key}.
                                        
                                        Call get_jira_issue_details with:
                                        - issue_key='{child_key}'
                                        
                                        Then analyze the issue's description and comments to create a summary that includes:
                                        
                                        1. WORK DONE: What specific work was completed in this issue?
                                        2. PURPOSE: What was this issue trying to achieve?
                                        3. RECENT ACTIVITY: What was done in the recent updates (based on comments and activity)?
                                        4. CURRENT STATUS: What is the current state of this issue?
                                        5. CHALLENGES: Any obstacles or problems encountered?
                                        
                                        CRITICAL INSTRUCTIONS FOR DATES:
                                        - NEVER mention any specific dates or timestamps in your summary
                                        - Only use the pre-formatted date "{child['updated_formatted']}" if you need to reference when this issue was last updated
                                        - DO NOT make up, infer, calculate, or guess any creation dates, resolution dates, or other dates
                                        - If you need to reference timing, use relative terms like "recently updated" instead of specific dates
                                        - Focus on the work content, not date details
                                        
                                        Focus on recent activity and what this issue contributes to the overall epic.
                                        Keep the summary concise but informative.
                                        """,
                                        agent=content_analyzer,
                                        expected_output=f"Summary of recent activity and purpose for issue {child_key}"
                                    )
                                    
                                    issue_crew = Crew(
                                        agents=[content_analyzer],
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
                                    
                                    epic_synthesis_task = Task(
                                        description=f"""
                                        Based on the following summaries of recently updated issues connected to epic {epic_key} ("{epic['summary']}"), 
                                        create a comprehensive epic-level summary:

                                        {issues_text}

                                        Create an epic summary that includes:
                                        
                                        1. EPIC OVERVIEW: What this epic is achieving based on connected issues
                                        2. RECENT PROGRESS: What work has been completed recently across connected issues  
                                        3. KEY ACCOMPLISHMENTS: Major achievements from the recently updated issues
                                        4. CURRENT FOCUS: What the team is currently working on
                                        5. CHALLENGES & BLOCKERS: Any issues or obstacles identified
                                        6. NEXT STEPS: What appears to be the planned next actions
                                        
                                        CRITICAL INSTRUCTIONS FOR DATES:
                                        - NEVER mention specific dates or timestamps in your epic summary
                                        - DO NOT make up, infer, calculate, or fabricate any creation dates, resolution dates, or other dates
                                        - Use only relative timing terms like "recently updated" or "recently completed"
                                        - The individual issue summaries above already contain properly formatted dates where needed
                                        - Focus on synthesizing the work content and progress, not date details
                                        
                                        Synthesize insights from all the connected issues to provide a holistic view of this epic's recent activity and progress.
                                        """,
                                        agent=content_analyzer,
                                        expected_output=f"Epic-level summary synthesized from recently updated connected issues"
                                    )
                                    
                                    epic_crew = Crew(
                                        agents=[content_analyzer],
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