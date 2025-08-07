# JIRA Dashboard and Reports

A comprehensive JIRA reporting and analysis system powered by CrewAI agents and MCP (Model Context Protocol) tools. This system generates detailed reports on epics, bugs, stories, and tasks with automated analysis and insights for any JIRA project.

## 🚀 Features

- **Epic Activity Analysis**: Track recent activity across epics and their connected issues
- **Critical/Blocker Bug Reports**: Analyze high-priority bugs with detailed summaries
- **Automated Story & Task Tracking**: Monitor progress on stories and tasks
- **Consolidated Summaries**: Generate comprehensive project status reports
- **Project-Agnostic**: Works with any JIRA project by specifying the project key
- **Configurable Time Periods**: Customize analysis timeframes (default: 14 days)
- **Mandatory Parameters**: Ensures correct project specification with required parameters

## 📋 System Requirements

- Python >=3.10 and <=3.13 (required by CrewAI)
- Access to JIRA MCP Snowflake server
- Environment variables configured (see setup section)

## 🚀 Quick Start

```bash
# 1. Set up environment
export GEMINI_API_KEY="your_gemini_api_key"
export SNOWFLAKE_TOKEN="your_snowflake_token"
export SNOWFLAKE_URL="your_jira_mcp_url"

# 2. Install dependencies
pip install crewai crewai-tools pyyaml

# 3. Run analysis for your project (replace YOUR_PROJECT with your JIRA project key and NUMBER_OF_DAYS with the number of days to look back for analysis )
python full_epic_activity_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
python consolidated_summary.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
python crewai_dashboard.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
```

⚠️ **Important**: All scripts now require the `--project` parameter to specify which JIRA project to analyze.

## 🛠️ Setup & Configuration

### 1. Environment Variables

Set the following environment variables:

```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
export SNOWFLAKE_TOKEN="your_snowflake_token_here"
export SNOWFLAKE_URL="jira_mcp_snowflake_url_here"
```

### 2. Install Dependencies

```bash
pip install crewai crewai-tools pyyaml
```

## 📊 Available Reports & Scripts

### 🔍 Epic Analysis Reports

#### `full_epic_activity_analysis.py`
**Purpose**: Analyzes epics with recent activity in related issues in a given time period

**What it does**:
- Finds all project epics in progress
- Identifies related issues with recent updates
- Generates detailed summaries for each epic with recent activity
- Creates comprehensive epic-level insights

**Usage**:
```bash
python full_epic_activity_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
```

**Parameters**:
- `--project` (required): JIRA project key to analyze (e.g., 'MYPROJ', 'TEAM')
- `--days` (optional): Number of days to look back for analysis (default: 14)

**Output**: 
- `recently_updated_epics_summary.txt` - Detailed epic summaries
- `{project}_full_epic_activity_analysis.json` - Raw analysis data

---

### 🐛 Bug Analysis Reports

#### `consolidated_summary.py`
**Purpose**: Comprehensive analysis of critical and blocker bugs with epic summaries

**Prerequisites**: 
⚠️ **IMPORTANT**: Must run `full_epic_activity_analysis.py` first to generate the epic summaries file

**What it does**:
- Fetches critical (priority=2) and blocker (priority=1) bugs from a given time period
- Analyzes each bug for problem details, resolution efforts, and current status
- Extracts epic summaries from existing analysis files
- Generates consolidated project status report
- Analyzes stories and tasks with recent activity

**Usage**:
```bash
# Run epic analysis first (required dependency)
python full_epic_activity_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS

# Then run consolidated summary
python consolidated_summary.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
```

**Parameters**:
- `--project` (required): JIRA project key to analyze (e.g., 'MYPROJ', 'TEAM')
- `--days` (optional): Number of days to look back for analysis (default: 14)

**Output**: 
- `{project}_consolidated_summary.txt` - Epic progress summary only
- `epic_summaries_only.txt` - Complete epic summaries for reference
- `epic_progress_analysis.txt` - Standalone epic progress analysis
- `{project}_bugs_analysis.txt` - Complete bugs analysis
- `{project}_stories_tasks_analysis.txt` - Stories and tasks analysis
- `blocker_bugs.json` - Raw blocker bug data
- `critical_bugs.json` - Raw critical bug data
- `stories.json` - Raw stories data
- `tasks.json` - Raw tasks data


### 🏢 Dashboard Reports

#### `crewai_dashboard.py`
**Purpose**: Generates comprehensive project dashboard

**What it does**:
- Fetches data across multiple JIRA issue types
- Creates unified dashboard view of project status
- Provides real-time insights into project health
- Calculates critical and blocker bug metrics
- Generates interactive HTML dashboard with charts

**Usage**:
```bash
python crewai_dashboard.py --project YOUR_PROJECT --days NUMBER_OF_DAYS
```

**Parameters**:
- `--project` (required): JIRA project key to analyze (e.g., 'MYPROJ', 'TEAM')
- `--days` (optional): Number of days to look back for analysis (default: 14)

**Output**: 
- `{project}_real_dashboard.html` - Interactive HTML dashboard
- `{project}_project_summary.json` - Project summary data
- `critical_bugs.json` - Critical bug metrics data
- `blocker_bugs.json` - Blocker bug metrics data

## ⚙️ Configuration System

The system uses YAML configuration files for maximum flexibility:

### `agents.yaml`
Defines AI agents with specific roles:
- **bug_analyzer**: Analyzes critical bugs and blockers
- **story_task_analyzer**: Analyzes stories and tasks
- **epic_progress_analyzer**: Analyzes epic progress
- **project_summary_analyst**: Analyzes overall project summaries
- **Various fetchers**: Specialized data retrieval agents for different issue types

### `tasks.yaml`
Defines tasks and workflows with dynamic parameter substitution:
- **Static tasks**: Pre-defined workflows for common operations
- **Template tasks**: Reusable task templates for dynamic creation
- **Epic analysis tasks**: Specialized epic analysis workflows
- **Configurable parameters**: Project names and timeframes are dynamically substituted

### `helper_func.py`
Utility functions including:
- Configuration loading and agent/task creation
- Date/timestamp formatting and validation
- JSON extraction and data processing
- Metrics calculation for items and bugs
- Project-agnostic filtering and processing functions

## 🤝 Contributing to the Project

### Getting Started
1. **Fork the repository** and clone your fork
2. **Set up environment variables** as described above
3. **Test the scripts** with your JIRA project to ensure connectivity

### Example Workflow
```bash
# Set environment variables
export GEMINI_API_KEY="your_api_key"
export SNOWFLAKE_TOKEN="your_token"
export SNOWFLAKE_URL="your_snowflake_url"

# Run epic analysis for your project
python full_epic_activity_analysis.py --project MYPROJ --days 7

# Generate consolidated summary
python consolidated_summary.py --project MYPROJ --days 7

# Create dashboard
python crewai_dashboard.py --project MYPROJ --days 7
```

### Development Guidelines

#### Code Standards
- Follow Python PEP 8 style guidelines
- Add docstrings to all functions and classes
- Include type hints where appropriate
- Write meaningful commit messages

#### Adding New Features

**For New Report Types**:
1. Define new agents in `agents.yaml` with clear roles and goals
2. Add corresponding tasks in `tasks.yaml` with specific instructions
3. Create new Python script using existing patterns from helper functions
4. Test thoroughly with real JIRA data

**For New Agents**:
1. Add agent definition to `agents.yaml`
2. Specify `requires_tools: true` if MCP tools are needed
3. Write clear backstory explaining the agent's expertise
4. Test agent behavior with various data scenarios

**For New Tasks**:
1. Add task definition to `tasks.yaml`
2. Use template substitution for reusable tasks
3. Specify clear expected outputs
4. Include proper error handling

#### Best Practices
**Testing**:
- Test with real JIRA data whenever possible
- Verify output file formats and content
- Check that all environment variables are properly used
- Test with different project keys to ensure project-agnostic functionality
- Verify mandatory parameters work correctly

**Security**:
- Never commit actual API keys or tokens
- Use placeholder values in example configurations
- Apply security credential check before commits

### Submitting Changes

1. **Create feature branch**: `git checkout -b feature/your-feature-name`
2. **Make changes** following the guidelines above
3. **Test thoroughly** with your JIRA environment
4. **Run security check** to ensure no credentials are exposed
5. **Commit with clear message**: Describe what the change does and why
6. **Submit pull request** with:
   - Clear description of changes
   - Testing performed
   - Any new dependencies or setup requirements
