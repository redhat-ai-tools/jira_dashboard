#!/usr/bin/env python3
"""
Epic Summary Generator
Reads the recently_updated_epics_summary.txt file and creates a consolidated epic progress summary.
Generates: {project}_consolidated_summary.txt with epic progress analysis only.
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
    parse_epic_summaries
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
    """Main function to create epic progress summary
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis (default: 14)
        projects (list): List of JIRA project keys to analyze (required)
    """
    if not projects:
        raise ValueError("Project parameter is required. Please specify JIRA project key(s) using --project.")
    
    # Normalize to uppercase and remove duplicates while preserving order
    projects = list(dict.fromkeys([p.upper() for p in projects]))
    
    print(f"🎯 Multi-Project Epic Summary Generator")
    print("="*80)
    print(f"📋 This will generate epic progress analysis from existing epic summaries for {len(projects)} project(s): {', '.join(projects)}")
    print(f"📄 Output files: [project]_consolidated_summary.txt for each project")
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
    """Create epic progress summary for a single project
    
    Args:
        analysis_period_days (int): Number of days to look back for analysis
        project (str): JIRA project key to analyze
    """
    print(f"🎯 {project} Epic Summary Generator")
    print("📋 Generating epic progress analysis from existing epic summaries")
    print(f"📄 Output file: {project.lower()}_consolidated_summary.txt")
    
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
            
            # Step 1: Parse existing epic summaries
            print("\n📖 Step 1: Reading existing epic summaries...")
            epic_summaries_file = f'{project.lower()}_recently_updated_epics_summary.txt'
            epic_summaries = parse_epic_summaries(epic_summaries_file)
            
            if not epic_summaries:
                print(f"❌ No epic summaries found for {project}. Cannot proceed.")
                print(f"💡 Please run full_epic_activity_analysis.py first for {project} to generate epic summaries.")
                raise FileNotFoundError(f"Epic summaries file not found: {epic_summaries_file}")
            
            # Save epic summaries to separate file for analysis
            print("💾 Saving epic summaries to separate file...")
            epic_summaries_filename = f'{project.lower()}_epic_summaries_only.txt'
            
            with open(epic_summaries_filename, 'w', encoding='utf-8') as f:
                f.write("EPIC SUMMARIES FOR ANALYSIS\n")
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
            
            # Step 2: Analyze epic progress for significant changes
            print(f"\n🎯 Step 2: Analyzing epic progress for significant changes and achievements...")
            
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
            epic_analysis_filename = f'{project.lower()}_epic_progress_analysis.txt'
            
            with open(epic_analysis_filename, 'w', encoding='utf-8') as f:
                f.write("EPIC PROGRESS ANALYSIS\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source: Analysis of {len(epic_summaries)} epic summaries\n")
                f.write("=" * 80 + "\n\n")
                f.write(epic_progress_analysis)
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("END OF ANALYSIS\n")
            
            print(f"✅ Epic progress analysis saved to: {epic_analysis_filename}")
            
            # Step 3: Generate consolidated summary (epics only)
            print(f"\n📄 Step 3: Generating consolidated summary...")
            
            output_filename = f'{project.lower()}_consolidated_summary.txt'
            
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(f"{project} CONSOLIDATED SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Analysis Period: Last {analysis_period_days} days\n")
                f.write(f"Note: See '{project.lower()}_bugs_analysis.txt' for detailed bugs analysis\n")
                f.write(f"Note: See '{project.lower()}_stories_tasks_analysis.txt' for stories/tasks analysis\n")
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
            print(f"   📅 Analysis period: Last {analysis_period_days} days")
            print(f"\n📄 OUTPUT FILES:")
            print(f"   📄 Consolidated summary (epics): {output_filename}")
            print(f"   📝 Epic summaries only: {epic_summaries_filename}")
            print(f"   🎯 Epic progress analysis: {epic_analysis_filename}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise  # Re-raise to be handled by the multi-project loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate epic progress summary analysis for one or more projects')
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
