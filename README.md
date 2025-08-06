# JIRA Dashboard for KONFLUX Project

A comprehensive JIRA reporting and analysis system for the KONFLUX project, powered by CrewAI agents and MCP (Model Context Protocol) tools. This system generates detailed reports on epics, bugs, stories, and tasks with automated analysis and insights.

## 🚀 Features

- **Epic Activity Analysis**: Track recent activity across epics and their connected issues
- **Critical/Blocker Bug Reports**: Analyze high-priority bugs with detailed summaries
- **Automated Story & Task Tracking**: Monitor progress on stories and tasks
- **Consolidated Summaries**: Generate comprehensive project status reports

## 📋 System Requirements

- Python 3.8+
- Access to JIRA MCP Snowflake server
- Environment variables configured (see setup section)

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
- Finds all KONFLUX epics in progress
- Identifies related issues with recent updates
- Generates detailed summaries for each epic with recent activity
- Creates comprehensive epic-level insights

**Usage**:
```bash
python full_epic_activity_analysis.py
```

**Output**: 
- `recently_updated_epics_summary.txt` - Detailed epic summaries
- `konflux_full_epic_activity_analysis.json` - Raw analysis data

---

### 🐛 Bug Analysis Reports

#### `consolidated_konflux_summary.py`
**Purpose**: Comprehensive analysis of critical and blocker bugs with epic summaries

**What it does**:
- Fetches critical (priority=2) and blocker (priority=1) bugs from a given time period
- Analyzes each bug for problem details, resolution efforts, and current status
- Extracts epic summaries from existing analysis files
- Generates consolidated project status report

**Usage**:
```bash
python consolidated_konflux_summary.py
```

**Output**: 
- `konflux_bugs_analysis.txt` - Detailed bug analysis report
- Various JSON files with raw bug data


### 🏢 Dashboard Reports

#### `crewai_konflux_dashboard.py`
**Purpose**: Generates comprehensive KONFLUX project dashboard

**What it does**:
- Fetches data across multiple JIRA issue types
- Creates unified dashboard view of project status
- Provides real-time insights into project health

**Usage**:
```bash
python crewai_konflux_dashboard.py
```

## ⚙️ Configuration System

The system uses YAML configuration files for maximum flexibility:

### `agents.yaml`
Defines AI agents with specific roles:
- **bug_analyzer**: Analyzes critical bugs and blockers
- **story_task_analyzer**: Analyzes stories and tasks
- **epic_progress_analyzer**: Analyzes epic progress
- **Various fetchers**: Specialized data retrieval agents

### `tasks.yaml`
Defines tasks and workflows:
- **Static tasks**: Pre-defined workflows for common operations
- **Template tasks**: Reusable task templates for dynamic creation
- **Epic analysis tasks**: Specialized epic analysis workflows

### `helper_func.py`
Utility functions including:
- Configuration loading and agent/task creation
- Date/timestamp formatting and validation
- JSON extraction and data processing
- Metrics calculation for items and bugs

## 🤝 Contributing to the Project

### Getting Started
1. **Fork the repository** and clone your fork
2. **Set up environment variables** as described above
3. **Test the scripts** with your JIRA access to ensure connectivity

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
