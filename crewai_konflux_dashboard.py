#!/usr/bin/env python3
"""
KONFLUX Dashboard Generator using CrewAI with MCP JIRA Snowflake Tools
Uses real MCP SSE server to fetch KONFLUX data - NO HARDCODED DATA
"""

import os
import json
import re
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter

# Configure Gemini LLM (as recommended in CrewAI SSE documentation)
gemini_api_key = os.getenv("GEMINI_API_KEY")
snowflake_token = os.getenv("SNOWFLAKE_TOKEN")
url = os.getenv("SNOWFLAKE_URL")

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=gemini_api_key,
    temperature=0.7,
)

# MCP Server configuration for JIRA Snowflake (SSE Server)
# Following the exact pattern from CrewAI MCP documentation
server_params = {
    "url": url,
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": snowflake_token 
    }
}

def create_jira_data_agent(mcp_tools):
    """Create an agent that fetches JIRA data using MCP tools"""
    return Agent(
        role="JIRA Data Analyst",
        goal="Fetch comprehensive KONFLUX project data from JIRA Snowflake using MCP tools",
        backstory="""You are a data analyst specializing in JIRA project analytics. 
        You use MCP JIRA Snowflake tools to extract real-time data about KONFLUX projects.
        You never use hardcoded data and always fetch fresh information from the database.""",
        tools=mcp_tools,
        llm=llm,
        verbose=True
    )

def create_dashboard_agent():
    """Create an agent that generates dashboard HTML"""
    return Agent(
        role="Dashboard Developer", 
        goal="Create a beautiful, interactive dashboard based on real KONFLUX data",
        backstory="""You are a frontend developer who creates stunning data visualizations.
        You take real JIRA data and transform it into interactive charts and dashboards 
        using modern web technologies like Plotly.js and responsive design.
        You return ONLY the complete HTML code without any markdown formatting.""",
        llm=llm,
        verbose=True
    )

def create_critical_bug_agent(mcp_tools):
    """Create an agent that fetches critical bug data"""
    return Agent(
        role="Critical Bug Analyst",
        goal="Fetch critical KONFLUX bugs and calculate metrics",
        backstory="""You are a specialist in critical bug analysis. You fetch critical priority bugs 
        from JIRA and provide precise counts for dashboard reporting.""",
        tools=mcp_tools,
        llm=llm,
        verbose=False
    )

def create_blocker_bug_agent(mcp_tools):
    """Create an agent that fetches blocker bug data"""
    return Agent(
        role="Blocker Bug Analyst",
        goal="Fetch blocker KONFLUX bugs and calculate metrics",
        backstory="""You are a specialist in blocker bug analysis. You fetch blocker priority bugs 
        from JIRA and provide precise counts for dashboard reporting.""",
        tools=mcp_tools,
        llm=llm,
        verbose=False
    )

def create_project_summary_agent(mcp_tools):
    """Create an agent that fetches project summary data"""
    return Agent(
        role="Project Summary Analyst",
        goal="Fetch comprehensive project summary from JIRA and filter for KONFLUX data",
        backstory="""You are a project analytics specialist who fetches comprehensive project 
        summaries from JIRA Snowflake and filters the data to focus on specific projects.""",
        tools=mcp_tools,
        llm=llm,
        verbose=False
    )

def filter_konflux_project_summary(project_summary_data):
    """Filter project summary data to only include KONFLUX project"""
    try:
        if isinstance(project_summary_data, str):
            import json
            project_summary_data = json.loads(project_summary_data)
        
        if not isinstance(project_summary_data, dict):
            return {"error": "Invalid project summary data format"}
        
        if "error" in project_summary_data:
            return project_summary_data
        
        projects = project_summary_data.get("projects", {})
        
        # Look for KONFLUX project (case-insensitive)
        konflux_project = None
        for project_name, project_data in projects.items():
            if project_name.upper() == "KONFLUX":
                konflux_project = project_data
                break
        
        if konflux_project is None:
            return {
                "error": "KONFLUX project not found in summary",
                "available_projects": list(projects.keys()),
                "total_projects_found": len(projects)
            }
        
        # Return filtered summary with only KONFLUX data
        return {
            "project_name": "KONFLUX",
            "total_issues": konflux_project.get("total_issues", 0),
            "statuses": konflux_project.get("statuses", {}),
            "priorities": konflux_project.get("priorities", {}),
            "summary": {
                "total_konflux_issues": konflux_project.get("total_issues", 0),
                "status_breakdown": konflux_project.get("statuses", {}),
                "priority_breakdown": konflux_project.get("priorities", {})
            }
        }
        
    except Exception as e:
        return {"error": f"Error filtering KONFLUX project summary: {str(e)}"}

class BugCalculator:
    """Universal bug calculation logic for any priority level"""
    
    def __init__(self, priority_ids, priority_name="Priority"):
        """
        Initialize calculator for specific priority levels
        
        Args:
            priority_ids: List of priority IDs to track (e.g., ["2"] for Critical, ["1"] for Blocker)
            priority_name: Human-readable name for the priority (e.g., "Critical", "Blocker")
        """
        self.priority_ids = priority_ids
        self.priority_name = priority_name
        self.bug_type_ids = ["1"]  # Bug type only
    
    def is_target_priority(self, priority):
        """Check if priority ID matches our target priority"""
        if not priority:
            return False
        return str(priority).strip() in self.priority_ids
    
    def is_bug_type(self, issue_type):
        """Check if issue type ID is a bug"""
        if not issue_type:
            return False
        return str(issue_type).strip() in self.bug_type_ids
    
    def is_resolved(self, resolution_date):
        """Check if issue is resolved using resolution_date field"""
        return resolution_date is not None and str(resolution_date).strip() != "" and str(resolution_date).strip().lower() != "null"
    
    def is_within_last_month(self, timestamp):
        """Check if timestamp is within the last 30 days"""
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
            
            # Check if within last 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            return dt >= cutoff_date
            
        except Exception as e:
            return False

    def extract_json_from_result(self, result_text):
        """Extract JSON data from CrewAI result"""
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
        
        # Try parsing as string
        result_str = str(result_text).strip()
        try:
            return json.loads(result_str)
        except:
            # Try extracting JSON with brace matching
            if result_str.startswith('{'):
                brace_count = 0
                in_string = False
                escape_next = False
                end_idx = -1
                
                for i, char in enumerate(result_str):
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\' and in_string:
                        escape_next = True
                        continue
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                
                if end_idx != -1:
                    json_str = result_str[:end_idx]
                    try:
                        return json.loads(json_str)
                    except:
                        pass
        
        return None

    def calculate_bug_metrics(self, issues):
        """Calculate the 3 key bug metrics for the configured priority"""
        priority_lower = self.priority_name.lower()
        metrics = {
            f'total_{priority_lower}_bugs': 0,
            f'total_{priority_lower}_bugs_resolved': 0,
            f'{priority_lower}_bugs_resolved_last_month': 0
        }
        
        bugs_fixed = []
        
        for issue in issues:
            issue_type = issue.get('issue_type', '')
            priority = issue.get('priority', '')
            resolution_date = issue.get('resolution_date', '')
            
            # Check if it's a target priority bug
            is_bug = self.is_bug_type(issue_type)
            is_target_priority = self.is_target_priority(priority) 
            is_resolved = self.is_resolved(resolution_date)
            
            if is_bug and is_target_priority:
                # 1. Total bugs of this priority
                metrics[f'total_{priority_lower}_bugs'] += 1
                
                if is_resolved:
                    # 2. Total bugs resolved (ever)
                    metrics[f'total_{priority_lower}_bugs_resolved'] += 1
                    
                    # 3. Bugs resolved in last month
                    if self.is_within_last_month(resolution_date):
                        metrics[f'{priority_lower}_bugs_resolved_last_month'] += 1
                        bugs_fixed.append({
                            'key': issue.get('key', 'N/A'),
                            'summary': issue.get('summary', 'N/A')[:100],
                            'resolution_date': resolution_date
                        })
        
        return metrics, bugs_fixed

    # Legacy method names for backward compatibility with existing code
    def calculate_critical_bug_metrics(self, issues):
        """Legacy method - use calculate_bug_metrics instead"""
        return self.calculate_bug_metrics(issues)
        
    def calculate_blocker_bug_metrics(self, issues):
        """Legacy method - use calculate_bug_metrics instead"""
        return self.calculate_bug_metrics(issues)

def extract_html_from_result(result_text):
    """Extract HTML content from CrewAI result"""
    # Convert result to string if it's not already
    result_str = str(result_text)
    
    # Look for HTML content between ```html and ``` or just starting with <!DOCTYPE
    html_patterns = [
        r'```html\s*(<!DOCTYPE.*?)```',
        r'(<!DOCTYPE html.*?)(?=```|\Z)',
        r'(<!DOCTYPE.*)',
    ]
    
    for pattern in html_patterns:
        match = re.search(pattern, result_str, re.DOTALL | re.IGNORECASE)
        if match:
            html_content = match.group(1).strip()
            # Clean up any remaining markdown artifacts
            html_content = re.sub(r'^```html\s*', '', html_content)
            html_content = re.sub(r'\s*```$', '', html_content)
            return html_content
    
    # If no HTML found, return the raw result
    return result_str

def main():
    """Main function to run the CrewAI workflow"""
    try:
        print("🚀 Starting KONFLUX Dashboard Generation with CrewAI...")
        print(f"📡 Connecting to MCP Server: {server_params['url']}")
        
        # Check if Gemini API key is available
        if not gemini_api_key:
            print("⚠️  Warning: GEMINI_API_KEY environment variable not set")
            print("💡 Please set GEMINI_API_KEY before running this script")
            create_fallback_dashboard()
            return
        
        # Connect to MCP server and get tools using context manager
        with MCPServerAdapter(server_params) as mcp_tools:
            print(f"✅ Connected! Available tools: {[tool.name for tool in mcp_tools]}")
            
            # Create agents
            data_agent = create_jira_data_agent(mcp_tools)
            critical_bug_agent = create_critical_bug_agent(mcp_tools)
            blocker_bug_agent = create_blocker_bug_agent(mcp_tools)
            project_summary_agent = create_project_summary_agent(mcp_tools)
            dashboard_agent = create_dashboard_agent()
            
            # Task 1: Fetch KONFLUX data using the actual MCP tool names
            fetch_data_task = Task(
                description="""
                Use the available MCP JIRA Snowflake tools to fetch comprehensive KONFLUX project data:
                
                1. Call the list_jira_issues tool with project='KONFLUX' to get all KONFLUX issues
                2. Call the list_jira_components tool with project='KONFLUX' and limit=1000 to get KONFLUX components
                3. Analyze and structure the data to extract key metrics:
                   - Total issues count by project
                   - Issues distribution by status (Open, Closed, In Progress, etc.)
                   - Issues distribution by priority (High, Medium, Low)
                   - Issues distribution by type (Bug, Story, Epic, Task, etc.)
                   - Recent activity patterns
                   - Component breakdown
                4. Format the results as structured JSON data ready for dashboard visualization
                5. Include real issue counts, not sample data
                """,
                agent=data_agent,
                expected_output="Structured JSON data containing real KONFLUX metrics and issue details from JIRA Snowflake"
            )
            
            # Task 2: Fetch Critical Bug Metrics
            fetch_critical_bugs_task = Task(
                description="""
                Use the list_jira_issues tool with these exact parameters:
                - project='KONFLUX'
                - priority='2' 
                - issue_type='1'
                - limit=1000
                
                Get Critical priority KONFLUX bugs with a limit of 1000 instead of the default 50.
                Return the complete result with all bug details.
                """,
                agent=critical_bug_agent,
                expected_output="JSON data containing Critical priority (priority=2) KONFLUX bugs from JIRA",
                output_file="critical_bug_metrics.json"
            )
            
            # Task 3: Fetch Blocker Bug Metrics  
            fetch_blocker_bugs_task = Task(
                description="""
                Use the list_jira_issues tool with these exact parameters:
                - project='KONFLUX'
                - priority='1' 
                - issue_type='1'
                - limit=1000
                
                Get Blocker priority KONFLUX bugs with a limit of 1000 instead of the default 50.
                Return the complete result with all bug details.
                """,
                agent=blocker_bug_agent,
                expected_output="JSON data containing Blocker priority (priority=1) KONFLUX bugs from JIRA",
                output_file="blocker_bug_metrics.json"
            )
            
            # Task 4: Fetch Project Summary and Filter for KONFLUX
            fetch_project_summary_task = Task(
                description="""
                Use the get_jira_project_summary tool to fetch comprehensive project statistics from JIRA Snowflake.
                This will return data for all projects with their statuses and priorities breakdown.
                After getting the result, filter the data to show only KONFLUX project information.
                
                The tool returns data in this format:
                {
                    "total_issues": number,
                    "total_projects": number, 
                    "projects": {
                        "PROJECT_NAME": {
                            "total_issues": number,
                            "statuses": {"status": count},
                            "priorities": {"priority": count}
                        }
                    }
                }
                
                Extract only the KONFLUX project data and return it in a clean format.
                """,
                agent=project_summary_agent,
                expected_output="JSON data containing KONFLUX project summary with status and priority breakdowns"
            )
            
            # Task 5: Generate dashboard
            generate_dashboard_task = Task(
                description="""
                Create a complete HTML dashboard using the real KONFLUX data, project summary, critical bug metrics, and blocker bug metrics.
                
                IMPORTANT: Return ONLY the complete HTML code without any markdown formatting or code blocks.
                
                Requirements:
                1. Create a clean, enterprise-style layout inspired by modern analytics dashboards
                2. Include a header with title "KONFLUX Impact Report" and current date
                3. Add a metrics summary section showing key statistics from project summary
                4. Add a dedicated Critical Bug Metrics tile/section with:
                   - Total Critical Bugs
                   - Total Critical Bugs Resolved
                   - Critical Bugs Resolved (Last Month)
                5. Add a dedicated Blocker Bug Metrics tile/section with:
                   - Total Blocker Bugs
                   - Total Blocker Bugs Resolved
                   - Blocker Bugs Resolved (Last Month)
                6. Generate interactive charts using Plotly.js CDN:
                   - Issues by status (bar chart) - use project summary data
                   - Issues by priority (pie chart) - use project summary data
                   - Issues by type (donut chart)
                   - Activity trends (horizontal bar chart for recent activity)
                   - Critical bug metrics (display as cards/tiles)
                6. Use a professional color scheme (blues, grays, whites)
                7. Make it responsive and mobile-friendly
                8. Include proper legends, tooltips, and data labels
                9. Embed the real JIRA data, project summary, critical bug metrics, and blocker bug metrics directly in the HTML as JavaScript objects
                10. IMPORTANT: Use the EXACT calculated critical and blocker bug metrics from their respective tasks, not hardcoded values
                11. Set the critical bug metrics values to:
                    - Total Critical Bugs: use actual count from critical bug data
                    - Total Resolved: use actual count from critical bug data  
                    - Resolved Last Month: use actual count from critical bug data (NOT hardcoded values)
                12. Set the blocker bug metrics values to:
                    - Total Blocker Bugs: use actual count from blocker bug data
                    - Total Resolved: use actual count from blocker bug data  
                    - Resolved Last Month: use actual count from blocker bug data (NOT hardcoded values)
                13. Use modern CSS with proper styling and highlight both critical and blocker bug sections
                14. Return the complete HTML starting with <!DOCTYPE html> and ending with </html>
                
                Do NOT wrap the HTML in markdown code blocks. Return the raw HTML only.
                """,
                agent=dashboard_agent,
                expected_output="Complete HTML file content ready to be saved directly as konflux_real_dashboard.html",
                context=[fetch_data_task, fetch_critical_bugs_task, fetch_blocker_bugs_task, fetch_project_summary_task]
            )
            
            # Create and run the crew
            crew = Crew(
                agents=[data_agent, critical_bug_agent, blocker_bug_agent, project_summary_agent, dashboard_agent],
                tasks=[fetch_data_task, fetch_critical_bugs_task, fetch_blocker_bugs_task, fetch_project_summary_task, generate_dashboard_task],
                verbose=True
            )
            
            print("🤖 Starting CrewAI workflow...")
            result = crew.kickoff()
            
            print("📝 Processing CrewAI result...")
            
            # Process project summary data if available
            project_summary_data = None
            try:
                # Get the project summary task result (fourth task in the crew)
                if hasattr(result, 'tasks_output') and len(result.tasks_output) >= 4:
                    project_summary_result = result.tasks_output[3]
                    
                    # Extract and filter project summary data
                    raw_summary = str(project_summary_result)
                    project_summary_data = filter_konflux_project_summary(raw_summary)
                    
                    if "error" not in project_summary_data:
                        print(f"📊 Project Summary Data:")
                        print(f"   Total KONFLUX Issues: {project_summary_data.get('total_issues', 0)}")
                        print(f"   Status Breakdown: {project_summary_data.get('statuses', {})}")
                        print(f"   Priority Breakdown: {project_summary_data.get('priorities', {})}")
                        
                        # Save project summary for potential use
                        with open('konflux_project_summary.json', 'w') as f:
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
            
            # Process critical bug data if available
            try:
                # Get the critical bug task result (second task in the crew)
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
                        with open('critical_bug_metrics.json', 'w') as f:
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
            
            # Process blocker bug data if available
            try:
                # Get the blocker bug task result (third task in the crew)
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
                        with open('blocker_bug_metrics.json', 'w') as f:
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
            if os.path.exists('critical_bug_metrics.json'):
                try:
                    with open('critical_bug_metrics.json', 'r') as f:
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
                    import re
                    html_content = re.sub(
                        r'const resolvedLastMonth = \d+;.*',
                        f'const resolvedLastMonth = {metrics["critical_bugs_resolved_last_month"]};',
                        html_content
                    )
                    
                    print("✅ HTML updated with correct calculated critical bug metrics")
                    
                except Exception as e:
                    print(f"⚠️  Could not update HTML with calculated critical bug metrics: {e}")
            else:
                print("⚠️  Critical bug metrics JSON file not found")
            
            # Fix the blocker bug metrics with actual calculated values
            if os.path.exists('blocker_bug_metrics.json'):
                try:
                    with open('blocker_bug_metrics.json', 'r') as f:
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
                print("⚠️  Blocker bug metrics JSON file not found")
            
            # Save the HTML file
            with open('konflux_real_dashboard.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print("✅ Dashboard generation completed!")
            print(f"📊 Dashboard saved as: konflux_real_dashboard.html")
            print(f"📏 HTML file size: {len(html_content)} characters")
            print("🔥 Critical bug metrics included in dashboard")
            print("🚫 Blocker bug metrics included in dashboard")
            
            # Verify the file was created properly
            if os.path.exists('konflux_real_dashboard.html'):
                file_size = os.path.getsize('konflux_real_dashboard.html')
                print(f"✅ File verification: {file_size} bytes written successfully")
            else:
                print("❌ File verification failed: File not found")
            
            return result
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("💡 Fallback: Creating dashboard with error message...")
        create_fallback_dashboard()

def create_fallback_dashboard():
    """Create a simple dashboard if MCP connection fails"""
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KONFLUX Dashboard - Connection Error</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 40px; 
            text-align: center; 
            background: #f5f5f5;
        }
        .error { 
            color: #d32f2f; 
            background: #ffebee; 
            padding: 30px; 
            border-radius: 12px; 
            border-left: 4px solid #d32f2f;
            max-width: 600px;
            margin: 0 auto;
        }
        h1 { margin-bottom: 20px; }
        p { margin: 10px 0; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="error">
        <h1>🔌 MCP Connection Error</h1>
        <p>Could not connect to JIRA Snowflake MCP server.</p>
        <p>Please check your network connection and server configuration.</p>
        <p><strong>Server:</strong> https://jira-mcp-snowflake.mcp-playground-poc.devshift.net/sse</p>
        <p><strong>API Key:</strong> Please ensure GEMINI_API_KEY is set in your environment</p>
    </div>
</body>
</html>'''
    
    with open('konflux_real_dashboard.html', 'w') as f:
        f.write(html_content)
    print("📄 Fallback dashboard created")

if __name__ == "__main__":
    main() 