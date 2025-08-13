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
pip install crewai crewai-tools crewai-tools[mcp] pyyaml
```

## 📊 Available Reports & Scripts

### `full_epic_activity_analysis.py`
**Purpose**: Analyzes epics in progress with recent activity in related issues in a given time period

**What it does**:
- Finds all project epics in progress
- Identifies related issues with recent updates
- Generates detailed summaries for each epic with recent activity
- Creates comprehensive epic-level insights

**Usage**:
```bash
# Single project
python full_epic_activity_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS

# Multiple projects
python full_epic_activity_analysis.py --project "PROJ1,PROJ2,PROJ3" --days NUMBER_OF_DAYS
```

**Parameters**:
- `--project` (required): JIRA project key(s) to analyze - single project or comma-separated list (e.g., 'MYPROJ' or 'PROJ1,PROJ2,PROJ3')
- `--days` (optional): Number of days to look back for analysis (default: 14)

**Output** (for each project): 
- `{project}_recently_updated_epics_summary.txt` - Detailed epic summaries
- `{project}_full_epic_activity_analysis.json` - Raw analysis data

---

### `bugs_analysis.py`
**Purpose**: Dedicated critical/blocker bugs analysis

**Usage**:
```bash
# Single project
python bugs_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS

# Multiple projects
python bugs_analysis.py --project "PROJ1,PROJ2,PROJ3" --days NUMBER_OF_DAYS
```

### `stories_tasks_analysis.py`
**Purpose**: Dedicated stories and tasks analysis

**Usage**:
```bash
# Single project
python stories_tasks_analysis.py --project YOUR_PROJECT --days NUMBER_OF_DAYS

# Multiple projects
python stories_tasks_analysis.py --project "PROJ1,PROJ2,PROJ3" --days NUMBER_OF_DAYS
```

### `epic_summary_generator.py`
**Purpose**: Dedicated epic progress analysis (requires epic summaries from full_epic_activity_analysis.py)

**Usage**:
```bash
# Single project
python epic_summary_generator.py --project YOUR_PROJECT --days NUMBER_OF_DAYS

# Multiple projects
python epic_summary_generator.py --project "PROJ1,PROJ2,PROJ3" --days NUMBER_OF_DAYS
```

**Parameters** (for all individual scripts):
- `--project` (required): JIRA project key(s) to analyze - single project or comma-separated list
- `--days` (optional): Number of days to look back for analysis (default: 14)

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


## Adding New Tasks

To add a new task, you need to update the YAML configuration and use the appropriate helper functions:

#### 1. Update `tasks.yaml`

Add your new task under the `tasks:` section:

```yaml
tasks:
  your_new_task:
    description: |
      Your task description here.
      
      Example task instructions:
      - Call the MCP tool with specific parameters
      - Return structured data in a specific format
      - Follow any output format requirements
   
    agent: "agent_name_from_agents_yaml"
    expected_output: "Description of expected output format"
    output_file: "optional_output_file.json"  # Optional
```

**Required fields:**
- `description`: Task instructions (can use template variables like `{project}`, `{timeframe}`)
- `agent`: Agent name that will execute this task
- `expected_output`: What the task should return

**Optional fields:**
- `output_file`: If the task should save output to a file
- Any custom fields your task needs

#### 2. Use Helper Functions

In your Python script, use these helper functions from `helper_func.py`:

```python
from helper_func import (
    load_tasks_config,
    create_task_from_config,
    create_agents
)

# Load task configuration
tasks_config = load_tasks_config()

# Create task with template variables
your_task = create_task_from_config(
    "your_new_task", 
    tasks_config['tasks']['your_new_task'], 
    agents_dict,
    project="YOUR_PROJECT",   # Will substitute {project}
    timeframe=14,             # Will substitute {timeframe}
    custom_var="custom_value" # Will substitute {custom_var}
)
```

**Available template variables:**
- `{project}`: Project key (e.g., "PROJECT")
- `{project_lower}`: Lowercase project key (e.g., "project")  
- `{timeframe}`: Analysis timeframe in days
- Any custom variables you pass to `create_task_from_config()`

## Adding New Agents

To add a new agent, you need to update the YAML configuration and use the appropriate helper functions:

#### 1. Update `agents.yaml`

Add your new agent under the `agents:` section:

```yaml
agents:
  your_new_agent:
    role: "Agent Role Title"
    goal: "What this agent aims to accomplish"
    backstory: |
      Detailed description of the agent's expertise and background.
      Explain what the agent specializes in and how it approaches tasks.
      
      Include any special instructions or constraints:
      - What tools the agent uses
      - How it formats responses
      - Any critical behavioral guidelines
    requires_tools: true  # true if agent needs tools, false otherwise
    verbose: true         # true for detailed output, false for quiet
```

**Required fields:**
- `role`: Short descriptive title
- `goal`: What the agent is trying to achieve
- `backstory`: Detailed agent description and instructions
- `requires_tools`: Boolean - whether agent needs access to MCP tools
- `verbose`: Boolean - whether agent should provide detailed output

#### 2. Use Helper Functions

In your Python script:

```python
from helper_func import (
    load_agents_config,
    create_agent_from_config,
    create_agents
)

# Option 1: Create all agents at once
agents = create_agents(mcp_tools, llm)
your_agent = agents['your_new_agent']

# Option 2: Create specific agent
agents_config = load_agents_config()
your_agent = create_agent_from_config(
    'your_new_agent',
    agents_config['agents']['your_new_agent'],
    mcp_tools,  # Pass MCP tools if requires_tools: true
    llm         # Pass LLM instance
)
```

### Example: Adding a New Bug Severity Task

1. **Add to `tasks.yaml`:**
```yaml
tasks:
  high_priority_bugs_task:
    description: |
      Fetch HIGH priority bugs from {project} project.
      
      Call list_jira_issues with:
      - project='{project}'
      - issue_type='1'
      - priority='3'
      - timeframe={timeframe}
      - limit=10
      
      Return only valid JSON from the MCP tool.
    agent: "bug_fetcher"
    expected_output: "Raw JSON data from list_jira_issues tool"
    output_file: "high_priority_bugs.json"
```

2. **Add to `agents.yaml` (if needed):**
```yaml
agents:
  bug_fetcher:
    role: "JIRA Bug Data Fetcher"
    goal: "Fetch bug data from JIRA efficiently"
    backstory: "You systematically retrieve bug data using MCP tools."
    requires_tools: true
    verbose: true
```

3. **Use in Python script:**
```python
# Load configurations
agents = create_agents(mcp_tools, llm)
tasks_config = load_tasks_config()

# Create task
high_priority_task = create_task_from_config(
    "high_priority_bugs_task",
    tasks_config['tasks']['high_priority_bugs_task'],
    agents,
    project="PROJ",
    timeframe=14
)

# Execute task
crew = Crew(
    agents=[agents['bug_fetcher']],
    tasks=[high_priority_task],
    verbose=True
)
result = crew.kickoff()
```



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
python full_epic_activity_analysis.py --project MYPROJ --days NUMBER_OF_DAYS

# Run individual analysis scripts as needed
python bugs_analysis.py --project MYPROJ --days NUMBER_OF_DAYS
python stories_tasks_analysis.py --project MYPROJ --days NUMBER_OF_DAYS
python epic_summary_generator.py --project MYPROJ --days NUMBER_OF_DAYS

# Create dashboard (requires additional setup - see dashboard section)
python crewai_dashboard.py --project MYPROJ --days NUMBER_OF_DAYS
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
