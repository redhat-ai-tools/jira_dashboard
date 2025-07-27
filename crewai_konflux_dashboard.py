#!/usr/bin/env python3
"""
KONFLUX Dashboard Generator using CrewAI with MCP JIRA Snowflake Tools
Uses real MCP SSE server to fetch KONFLUX data - NO HARDCODED DATA
"""

import os
import json
import re
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter

# Configure Gemini LLM (as recommended in CrewAI SSE documentation)
gemini_api_key = os.getenv("GEMINI_API_KEY")

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=gemini_api_key,
    temperature=0.7,
)

# MCP Server configuration for JIRA Snowflake (SSE Server)
# Following the exact pattern from CrewAI MCP documentation
server_params = {
    "url": "https://jira-mcp-snowflake.mcp-playground-poc.devshift.net/sse",
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": "token"
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
            dashboard_agent = create_dashboard_agent()
            
            # Task 1: Fetch KONFLUX data using the actual MCP tool names
            fetch_data_task = Task(
                description="""
                Use the available MCP JIRA Snowflake tools to fetch comprehensive KONFLUX project data:
                
                1. Call the list_jira_issues tool with project='KONFLUX' to get all KONFLUX issues
                2. Call the get_jira_project_summary tool to get project overview  
                3. Call the list_jira_components tool with search_text='konflux' to get KONFLUX components
                4. Analyze and structure the data to extract key metrics:
                   - Total issues count by project
                   - Issues distribution by status (Open, Closed, In Progress, etc.)
                   - Issues distribution by priority (High, Medium, Low)
                   - Issues distribution by type (Bug, Story, Epic, Task, etc.)
                   - Recent activity patterns
                   - Component breakdown
                5. Format the results as structured JSON data ready for dashboard visualization
                6. Include real issue counts, not sample data
                """,
                agent=data_agent,
                expected_output="Structured JSON data containing real KONFLUX metrics and issue details from JIRA Snowflake"
            )
            
            # Task 2: Generate dashboard
            generate_dashboard_task = Task(
                description="""
                Create a complete HTML dashboard using the real KONFLUX data fetched from JIRA.
                
                IMPORTANT: Return ONLY the complete HTML code without any markdown formatting or code blocks.
                
                Requirements:
                1. Create a clean, enterprise-style layout inspired by modern analytics dashboards
                2. Include a header with title "KONFLUX Impact Report" and current date
                3. Add a metrics summary section showing key statistics
                4. Generate interactive charts using Plotly.js CDN:
                   - Issues by status (bar chart)
                   - Issues by priority (pie chart) 
                   - Issues by type (donut chart)
                   - Activity trends (horizontal bar chart for recent activity)
                5. Use a professional color scheme (blues, grays, whites)
                6. Make it responsive and mobile-friendly
                7. Include proper legends, tooltips, and data labels
                8. Embed the real JIRA data directly in the HTML as a JavaScript object
                9. Use modern CSS with proper styling
                10. Return the complete HTML starting with <!DOCTYPE html> and ending with </html>
                
                Do NOT wrap the HTML in markdown code blocks. Return the raw HTML only.
                """,
                agent=dashboard_agent,
                expected_output="Complete HTML file content ready to be saved directly as konflux_real_dashboard.html",
                context=[fetch_data_task]
            )
            
            # Create and run the crew
            crew = Crew(
                agents=[data_agent, dashboard_agent],
                tasks=[fetch_data_task, generate_dashboard_task],
                verbose=True
            )
            
            print("🤖 Starting CrewAI workflow...")
            result = crew.kickoff()
            
            print("📝 Processing CrewAI result...")
            
            # Extract HTML from the result
            html_content = extract_html_from_result(result)
            
            # Save the HTML file
            with open('konflux_real_dashboard.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print("✅ Dashboard generation completed!")
            print(f"📊 Dashboard saved as: konflux_real_dashboard.html")
            print(f"📏 HTML file size: {len(html_content)} characters")
            
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