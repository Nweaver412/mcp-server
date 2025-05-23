"""Prompt templates for generating data app scripts."""

from typing import Optional

# List of pre-installed libraries that can be used in the data app
PRE_INSTALLED_LIBRARIES = [
    "streamlit",
    "pandas",
    "numpy",
    "plotly",
    "matplotlib",
    "seaborn",
    "scikit-learn",
    "altair",
    "streamlit-aggrid",
    "streamlit-authenticator",
    "streamlit-keboola-api",
    "pydeck",
    "extra-streamlit-components"
]

class DataAppPrompt:
    """Template for generating data app prompts."""
    
    # Format the libraries list for the prompt
    _LIBRARIES_LIST = "\n".join(f"- {lib}" for lib in PRE_INSTALLED_LIBRARIES)
    
    _TEMPLATE = f"""Generate a Streamlit script for a data app named '{{name}}' that {{description}}.

User Query: {{user_query}}

Pre-installed Libraries:
{_LIBRARIES_LIST}

Requirements:
- Use Streamlit for data visualization or interaction
- Include proper error handling
- Add helpful comments
- Follow Python best practices
- Use Keboola's CommonInterface for data access:
   - Use ci = CommonInterface() for data access
   - Use ci.get_input_tables_definitions() to get table definitions
   - Use ci.get_input_tables() to read data
   - Handle table paths and CSV reading properly
- Make the UI clean and user-friendly
- Include data validation and error handling for missing or invalid data
- Add appropriate visualizations based on the data types
- Include filters and interactive elements where appropriate


Please provide only the Python code, no explanations. The code should:
- Initialize Keboola CommonInterface for data access
- Handle the specific data tables mentioned in the user query or description
- Create appropriate visualizations based on the data
- Include proper error handling for data access and processing
- Follow Streamlit best practices for UI/UX
- Use proper Keboola data access patterns"""

    @classmethod
    def format(cls, name: str, description: str, user_query: Optional[str] = None) -> str:
        """
        Format the prompt template with the given parameters.
        
        Args:
            name: Name of the data app
            description: Description of what the data app should do
            user_query: Optional query about what data to use
            
        Returns:
            Formatted prompt string for generating the data app script
        """
        return cls._TEMPLATE.format(
            name=name,
            description=description,
            user_query=user_query if user_query else 'No specific query provided'
        ) 