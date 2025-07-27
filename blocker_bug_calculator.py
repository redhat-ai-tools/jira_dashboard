#!/usr/bin/env python3
"""
Blocker Bug Fix Calculator - Programmatic Tool (FIXED for numeric IDs)
Fetches JIRA data using MCP tools and calculates Blocker bug fixes using Python code (no LLM math)
"""

import os
import json
import re
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, LLM
from crewai_tools import MCPServerAdapter

# Configure Gemini LLM (minimal usage for data fetching only)
gemini_api_key = os.getenv("GEMINI_API_KEY")

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=gemini_api_key,
    temperature=0.1,  # Very low temperature for data fetching
)

# MCP Server configuration for JIRA Snowflake
server_params = {
    "url": "https://jira-mcp-snowflake.mcp-playground-poc.devshift.net/sse",
    "transport": "sse",
    "headers": {
        "X-Snowflake-Token": "token"
    }
}

class BlockerBugCalculator:
    """Programmatic calculator for Blocker bug fixes with CORRECT numeric ID mappings"""
    
    def __init__(self):
        # CORRECT priority mappings from user:
        # 10200 - priority normal
        # 2 - priority Blocker  
        # 10300 - priority undefined
        # 3 - priority major
        # 4 - priority minor
        # 1 - blocker
        # USER SPECIFIED: Only count priority='1' (Blocker) bugs
        self.blocker_priority_ids = [
            "1",    # Blocker (only this one as per user request)
        ]
        
        # CORRECT bug type from user:
        # issue_type: 1 = bug
        self.bug_type_ids = [
            "1",     # Bug (confirmed by user)
        ]
    
    def is_blocker_priority(self, priority):
        """Check if priority ID indicates a Blocker bug"""
        if not priority:
            return False
        return str(priority).strip() in self.blocker_priority_ids
    
    def is_bug_type(self, issue_type):
        """Check if issue type ID is a bug"""
        if not issue_type:
            return False
        return str(issue_type).strip() in self.bug_type_ids
    
    def is_resolved(self, resolution_date):
        """Check if issue is resolved using resolution_date field (user specified method)"""
        # User specified: resolution_date - not null indicates resolved
        return resolution_date is not None and str(resolution_date).strip() != "" and str(resolution_date).strip().lower() != "null"
    
    def is_within_last_month(self, timestamp):
        """Check if timestamp is within the last 30 days"""
        if not timestamp:
            return False
        
        try:
            # Handle the specific format from JIRA: "1753460716.477000000 1440"
            if isinstance(timestamp, str):
                # Extract the first part (Unix timestamp)
                timestamp_parts = timestamp.strip().split()
                if timestamp_parts:
                    timestamp_str = timestamp_parts[0]
                    # Handle decimal Unix timestamps
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
            print(f"⚠️  Error parsing timestamp {timestamp}: {e}")
            return False

    def create_data_fetcher_agent(self, mcp_tools):
        """Create a minimal agent just to fetch JIRA data"""
        return Agent(
            role="Data Fetcher",
            goal="Fetch raw KONFLUX issues data from JIRA using MCP tools",
            backstory="You are a simple data fetcher that returns raw JSON data without any analysis.",
            tools=mcp_tools,
            llm=llm,
            verbose=True
        )

    def extract_json_from_result(self, result_text):
        """Extract JSON data from CrewAI result - ROBUST PARSING"""
        # Silently process the result
        
        # Method 1: Check if result_text is already a dict/JSON object
        if isinstance(result_text, dict):
            print("✅ Result is already a dictionary")
            return result_text
        
        # Method 2: Check if it has a raw attribute (CrewAI result object)
        if hasattr(result_text, 'raw'):
            if isinstance(result_text.raw, dict):
                print("✅ JSON extracted successfully")
                return result_text.raw
            elif isinstance(result_text.raw, str):
                # Try to extract JSON from .raw string
                return self._extract_json_from_string(result_text.raw)
        
        # Method 3: Convert to string and extract JSON
        result_str = str(result_text).strip()
        return self._extract_json_from_string(result_str)
    
    def _extract_json_from_string(self, text):
        """Extract JSON from a string that may have extra content - ROBUST ALGORITHM"""
        try:
            # Method A: Try parsing the whole string as JSON first
            data = json.loads(text)
            print("✅ Parsed entire string as JSON")
            return data
        except json.JSONDecodeError as e:
            # Try alternative extraction methods
            pass
            
        # Method B: Smart JSON extraction with proper string handling
        text = text.strip()
        if text.startswith('{'):
            
            # Find the end of the JSON object by properly handling strings
            brace_count = 0
            in_string = False
            escape_next = False
            end_idx = -1
            
            for i, char in enumerate(text):
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
                json_str = text[:end_idx]
                try:
                    data = json.loads(json_str)
                    print("✅ JSON extracted successfully")
                    return data
                except json.JSONDecodeError as e:
                    pass
        
        # Method C: Try to find JSON by looking for "issues" key pattern
        # Match from { to the end of the issues array
        issues_pattern = r'(\{[^{}]*?"issues"\s*:\s*\[.*?\][^{}]*?\})'
        
        # Try with non-greedy matching for large content
        try:
            # Look for the pattern but be more specific about the end
            start_idx = text.find('{"issues":')
            if start_idx == -1:
                start_idx = text.find('{ "issues":')
            if start_idx == -1:
                start_idx = text.find('{\\n  "issues":')
                
            if start_idx != -1:
                # Extract from start position and try to find the end
                remaining_text = text[start_idx:]
                
                # Use the smart brace matching on the remaining text
                brace_count = 0
                in_string = False
                escape_next = False
                end_idx = -1
                
                for i, char in enumerate(remaining_text):
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
                    json_str = remaining_text[:end_idx]
                    try:
                        data = json.loads(json_str)
                        print("✅ JSON extracted successfully")
                        return data
                    except json.JSONDecodeError as e:
                        pass
        except Exception as e:
            pass
        
        print(f"❌ Could not extract JSON from result")
        return None
    
    def fetch_konflux_issues(self, mcp_tools):
        """Fetch KONFLUX issues using CrewAI agent with MCP tools"""
        print("📥 Fetching Blocker bugs...")
        
        try:
            # Create a simple data fetcher agent
            data_agent = self.create_data_fetcher_agent(mcp_tools)
            
            # Task to fetch raw KONFLUX data by priority (to get complete historical data)
            fetch_task = Task(
                description="""
                Fetch Blocker priority KONFLUX BUGS:
                
                Use list_jira_issues with project='KONFLUX' and priority='1' and issue_type='1' and limit=1000
                (Only Blocker priority bugs - not Blocker, Major, or other priorities)
                
                Return the complete result with all Blocker priority bug details.
                This approach ensures we get the complete historical set of Blocker issues, not just recent ones.
                
                Return the combined data as a single JSON object with format: {"issues": [...all issues...]}
                """,
                agent=data_agent,
                expected_output="JSON data containing Blocker priority (priority=1) KONFLUX bugs from JIRA"
            )
            
            # Create minimal crew for data fetching
            crew = Crew(
                agents=[data_agent],
                tasks=[fetch_task],
                verbose=True
            )
            
            # Fetch data using CrewAI agent
            result = crew.kickoff()
            
            # Extract JSON from result
            data = self.extract_json_from_result(result)
            
            if data:
                # Handle different data structures
                if isinstance(data, dict) and 'issues' in data:
                    issues = data['issues']
                elif isinstance(data, list):
                    issues = data
                else:
                    print(f"⚠️  Unexpected data format: {type(data)}")
                    return []
                
                print(f"✅ Found {len(issues)} Blocker bugs")
                return issues
            else:
                print("❌ Could not parse issues data")
                return []
                
        except Exception as e:
            print(f"❌ Error fetching issues: {e}")
            return []
    
    def calculate_blocker_bug_fixes(self, issues):
        """Calculate Blocker bug fixes from issues data - Pure Python logic with CORRECT mappings"""
        print("🔢 Analyzing Blocker bugs...")
        
        blocker_bugs_fixed = []
        stats = {
            'total_issues': len(issues),
            'total_bugs': 0,
            'blocker_priority_issues': 0,
            'resolved_issues': 0,
            'recent_resolved': 0,
            'blocker_bugs_fixed_last_month': 0
        }
        
        # Debug counters for analysis
        priority_counts = {}
        issue_type_counts = {}
        status_counts = {}
        
        # Track Blocker bugs for debugging
        all_blocker_bugs = []
        resolved_blocker_bugs = []
        
        for issue in issues:
            # Extract fields safely
            issue_type = issue.get('issue_type', '')
            priority = issue.get('priority', '')
            status = issue.get('status', '')
            resolution = issue.get('resolution')
            updated = issue.get('updated', '')
            resolution_date = issue.get('resolution_date', '')
            
            # Count for debugging
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count all bugs (using correct numeric ID)
            if self.is_bug_type(issue_type):
                stats['total_bugs'] += 1
            
            # Count Blocker priority issues
            if self.is_blocker_priority(priority):
                stats['blocker_priority_issues'] += 1
            
            # Count resolved issues (using resolution_date as specified by user)
            if self.is_resolved(resolution_date):
                stats['resolved_issues'] += 1
                
                # Check if resolved recently
                if self.is_within_last_month(resolution_date):
                    stats['recent_resolved'] += 1
            
            # Track all Blocker bugs for debugging
            is_bug = self.is_bug_type(issue_type)
            is_blocker = self.is_blocker_priority(priority) 
            is_resolved = self.is_resolved(resolution_date)
            
            if is_bug and is_blocker:
                bug_info = {
                    'key': issue.get('key', 'N/A'),
                    'summary': issue.get('summary', 'N/A')[:80],
                    'priority': priority,
                    'issue_type': issue_type,
                    'resolution_date': resolution_date,
                    'is_resolved': is_resolved,
                    'is_recent': self.is_within_last_month(resolution_date) if is_resolved else False
                }
                all_blocker_bugs.append(bug_info)
                
                if is_resolved:
                    resolved_blocker_bugs.append(bug_info)
                    
                    # Check if resolved in last month using resolution_date
                    if self.is_within_last_month(resolution_date):
                        stats['blocker_bugs_fixed_last_month'] += 1
                        blocker_bugs_fixed.append({
                            'key': issue.get('key', 'N/A'),
                            'summary': issue.get('summary', 'N/A')[:100],
                            'priority': priority,
                            'status': status,
                            'resolution': resolution,
                            'resolution_date': resolution_date,
                            'issue_type': issue_type
                        })
        
        return stats, blocker_bugs_fixed
    
    def run_analysis(self):
        """Run the complete Blocker bug analysis"""
        print("🔍 Starting Blocker Bug Analysis...")
        print("📡 Connecting to JIRA...")
        
        # Check if Gemini API key is available
        if not gemini_api_key:
            print("⚠️  Warning: GEMINI_API_KEY environment variable not set")
            return None
        
        try:
            # Connect to MCP server
            with MCPServerAdapter(server_params) as mcp_tools:
                # Connected successfully
                
                # Fetch KONFLUX issues using CrewAI agent
                issues = self.fetch_konflux_issues(mcp_tools)
                
                if not issues:
                    print("❌ No issues fetched, cannot perform analysis")
                    return None
                
                # Calculate Blocker bug fixes (pure Python logic)
                stats, blocker_bugs = self.calculate_blocker_bug_fixes(issues)
                
                # Display simplified results
                print("\n" + "="*50)
                print("📊 Blocker BUG ANALYSIS (Priority=1)")
                print("="*50)
                print(f"🔥 Total Blocker Bugs Found: {stats['blocker_priority_issues']}")
                print(f"🎯 Blocker Bugs Fixed (Last 30 Days): {stats['blocker_bugs_fixed_last_month']}")
                print("="*50)
                
                if blocker_bugs:
                    print(f"\n🔥 Blocker Bugs Fixed in Last Month ({len(blocker_bugs)}):")
                    print("-" * 50)
                    for i, bug in enumerate(blocker_bugs, 1):
                        print(f"{i}. {bug['key']}: {bug['summary']}")
                else:
                    print("\n💡 No Blocker bugs were fixed in the last month.")
                
                # Return structured result
                result = {
                    'blocker_bugs_fixed_last_month': stats['blocker_bugs_fixed_last_month'],
                    'statistics': stats,
                    'blocker_bugs_list': blocker_bugs,
                    'analysis_date': datetime.now().isoformat(),
                    'calculation_method': 'programmatic_python_priority_1_only'
                }
                
                return result
                
        except Exception as e:
            print(f"❌ Error during analysis: {e}")
            return None

def save_analysis_report(result):
    """Save analysis result to JSON file"""
    if result:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"blocker_bugs_analysis_priority1_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Analysis report saved to: {filename}")
        return filename
    return None

if __name__ == "__main__":
    # Create calculator instance
    calculator = BlockerBugCalculator()
    
    # Run analysis
    result = calculator.run_analysis()
    
    # Save report and show final result
    if result:
        report_file = save_analysis_report(result)
        print(f"\n🎯 FINAL RESULT: {result['blocker_bugs_fixed_last_month']} Blocker bugs fixed in the last month")
        print(f"📊 Full report saved as: {report_file}")
    else:
        print("❌ Analysis failed") 
