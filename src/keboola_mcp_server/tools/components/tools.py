import logging
from typing import Annotated, Sequence, Optional, List, Dict, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from keboola_mcp_server.client import KeboolaClient
from keboola_mcp_server.tools.components.model import (
    ComponentConfiguration,
    ComponentType,
    ComponentWithConfigurations,
    DataApp,
    DataAppConfiguration,
)
from keboola_mcp_server.tools.components.utils import (
    _get_component_details,
    _get_sql_transformation_id_from_sql_dialect,
    _get_transformation_configuration,
    _handle_component_types,
    _retrieve_components_configurations_by_ids,
    _retrieve_components_configurations_by_types,
)
from keboola_mcp_server.tools.storage import retrieve_buckets, retrieve_bucket_tables
from keboola_mcp_server.tools.sql import get_sql_dialect, query_table

LOG = logging.getLogger(__name__)


############################## Add component tools to the MCP server #########################################

# Regarding the conventional naming of entity models for components and their associated configurations,
# we also unified and shortened function names to make them more intuitive and consistent for both users and LLMs.
# These tool names now reflect their conventional usage, removing redundant parts for users while still
# providing the same functionality as described in the original tool names.
RETRIEVE_COMPONENTS_CONFIGURATIONS_TOOL_NAME: str = 'retrieve_components'
RETRIEVE_TRANSFORMATIONS_CONFIGURATIONS_TOOL_NAME: str = 'retrieve_transformations'
GET_COMPONENT_CONFIGURATION_DETAILS_TOOL_NAME: str = 'get_component_details'


def add_component_tools(mcp: FastMCP) -> None:
    """Add tools to the MCP server."""

    mcp.add_tool(
        get_component_configuration_details, name=GET_COMPONENT_CONFIGURATION_DETAILS_TOOL_NAME
    )
    LOG.info(f'Added tool: {GET_COMPONENT_CONFIGURATION_DETAILS_TOOL_NAME}.')

    mcp.add_tool(
        retrieve_components_configurations, name=RETRIEVE_COMPONENTS_CONFIGURATIONS_TOOL_NAME
    )
    LOG.info(f'Added tool: {RETRIEVE_COMPONENTS_CONFIGURATIONS_TOOL_NAME}.')

    mcp.add_tool(
        retrieve_transformations_configurations,
        name=RETRIEVE_TRANSFORMATIONS_CONFIGURATIONS_TOOL_NAME,
    )
    LOG.info(f'Added tool: {RETRIEVE_TRANSFORMATIONS_CONFIGURATIONS_TOOL_NAME}.')

    mcp.add_tool(create_sql_transformation)
    LOG.info(f'Added tool: {create_sql_transformation.__name__}.')

    mcp.add_tool(create_data_app)
    LOG.info('Added tool: create_data_app.')

    LOG.info('Component tools initialized.')


############################## read tools #########################################


async def retrieve_components_configurations(
    ctx: Context,
    component_types: Annotated[
        Sequence[ComponentType],
        Field(
            description='List of component types to filter by. If none, return all components.',
        ),
    ] = tuple(),
    component_ids: Annotated[
        Sequence[str],
        Field(
            description='List of component IDs to retrieve configurations for. If none, return all components.',
        ),
    ] = tuple(),
) -> Annotated[
    list[ComponentWithConfigurations],
    Field(
        description='List of objects, each containing a component and its associated configurations.',
    ),
]:
    """
    Retrieves components configurations in the project, optionally filtered by component types or specific component IDs
    If component_ids are supplied, only those components identified by the IDs are retrieved, disregarding
    component_types.
    USAGE:
        - Use when you want to see components configurations in the project for given component_types.
        - Use when you want to see components configurations in the project for given component_ids.
    EXAMPLES:
        - user_input: `give me all components`
            -> returns all components configurations in the project
        - user_input: `list me all extractor components`
            -> set types to ["extractor"]
            -> returns all extractor components configurations in the project
        - user_input: `give me configurations for following component/s` | `give me configurations for this component`
            -> set component_ids to list of identifiers accordingly if you know them
            -> returns all configurations for the given components
        - user_input: `give me configurations for 'specified-id'`
            -> set component_ids to ['specified-id']
            -> returns the configurations of the component with ID 'specified-id'
    """
    # If no component IDs are provided, retrieve component configurations by types (default is all types)
    if not component_ids:
        client = KeboolaClient.from_state(ctx.session.state)
        component_types = _handle_component_types(component_types)  # if none, return all types
        return await _retrieve_components_configurations_by_types(client, component_types)
    # If component IDs are provided, retrieve component configurations by IDs
    else:
        client = KeboolaClient.from_state(ctx.session.state)
        return await _retrieve_components_configurations_by_ids(client, component_ids)


async def retrieve_transformations_configurations(
    ctx: Context,
    transformation_ids: Annotated[
        Sequence[str],
        Field(
            description='List of transformation component IDs to retrieve configurations for.',
        ),
    ] = tuple(),
) -> Annotated[
    list[ComponentWithConfigurations],
    Field(
        description='List of objects, each containing a transformation component and its associated configurations.',
    ),
]:
    """
    Retrieves transformations configurations in the project, optionally filtered by specific transformation IDs.
    USAGE:
        - Use when you want to see transformation configurations in the project for given transformation_ids.
        - Use when you want to retrieve all transformation configurations, then set transformation_ids to an empty list.
    EXAMPLES:
        - user_input: `give me all transformations`
            -> returns all transformation configurations in the project
        - user_input: `give me configurations for following transformation/s` | `give me configurations for
        this transformation`
            -> set transformation_ids to list of identifiers accordingly if you know the IDs
            -> returns all transformation configurations for the given transformations IDs
        - user_input: `list me transformations for this transformation component 'specified-id'`
            -> set transformation_ids to ['specified-id']
            -> returns the transformation configurations with ID 'specified-id'
    """
    # If no transformation IDs are provided, retrieve transformations configurations by transformation type
    if not transformation_ids:
        client = KeboolaClient.from_state(ctx.session.state)
        return await _retrieve_components_configurations_by_types(client, ['transformation'])
    # If transformation IDs are provided, retrieve transformations configurations by IDs
    else:
        client = KeboolaClient.from_state(ctx.session.state)
        return await _retrieve_components_configurations_by_ids(client, transformation_ids)


async def get_component_configuration_details(
    component_id: Annotated[
        str, Field(description='Unique identifier of the Keboola component/transformation')
    ],
    configuration_id: Annotated[
        str,
        Field(
            description='Unique identifier of the Keboola component/transformation configuration you want details '
            'about',
        ),
    ],
    ctx: Context,
) -> Annotated[
    ComponentConfiguration,
    Field(
        description='Detailed information about a Keboola component/transformation and its configuration.',
    ),
]:
    """
    Gets detailed information about a specific Keboola component configuration given component/transformation ID and
    configuration ID.
    USAGE:
        - Use when you want to see the details of a specific component/transformation configuration.
    EXAMPLES:
        - user_input: `give me details about this configuration`
            -> set component_id and configuration_id to the specific component/transformation ID and configuration ID
            if you know it
            -> returns the details of the component/transformation configuration pair
    """

    client = KeboolaClient.from_state(ctx.session.state)

    # Get Component Details
    component = await _get_component_details(client=client, component_id=component_id)
    # Get Configuration Details
    raw_configuration = client.storage_client_sync.configurations.detail(
        component_id, configuration_id
    )
    LOG.info(
        f'Retrieved configuration details for {component_id} component with configuration {configuration_id}.'
    )

    # Get Configuration Metadata if exists
    endpoint = f'branch/{client.storage_client_sync._branch_id}/components/{component_id}/configs/{configuration_id}/metadata'
    r_metadata = await client.storage_client.get(endpoint)
    if r_metadata:
        LOG.info(
            f'Retrieved configuration metadata for {component_id} component with configuration {configuration_id}.'
        )
    else:
        LOG.info(
            f'No metadata found for {component_id} component with configuration {configuration_id}.'
        )
    # Create Component Configuration Detail Object
    return ComponentConfiguration.model_validate(
        {
            **raw_configuration,
            'component': component,
            'component_id': component_id,
            'metadata': r_metadata,
        }
    )


async def create_sql_transformation(
    ctx: Context,
    name: Annotated[
        str,
        Field(
            description='A short, descriptive name summarizing the purpose of the SQL transformation.',
        ),
    ],
    description: Annotated[
        str,
        Field(
            description=(
                'The detailed description of the SQL transformation capturing the user intent, explaining the '
                'SQL query, and the expected output.'
            ),
        ),
    ],
    sql_statements: Annotated[
        Sequence[str],
        Field(
            description=(
                'The executable SQL query statements written in the current SQL dialect. '
                'Each statement should be a separate item in the list.'
            ),
        ),
    ],
    created_table_names: Annotated[
        Sequence[str],
        Field(
            description=(
                'An empty list or a list of created table names if and only if they are generated within SQL '
                'statements (e.g., using `CREATE TABLE ...`).'
            ),
        ),
    ] = tuple(),
) -> Annotated[
    ComponentConfiguration,
    Field(
        description='Newly created SQL Transformation Configuration.',
    ),
]:
    """
    Creates an SQL transformation using the specified name, SQL query following the current SQL dialect, a detailed
    description, and optionally a list of created table names if and only if they are generated within the SQL
    statements.
    CONSIDERATIONS:
        - The SQL query statement is executable and must follow the current SQL dialect, which can be retrieved using
        appropriate tool.
        - When referring to the input tables within the SQL query, use fully qualified table names, which can be
          retrieved using appropriate tools.
        - When creating a new table within the SQL query (e.g. CREATE TABLE ...), use only the quoted table name without
          fully qualified table name, and add the plain table name without quotes to the `created_table_names` list.
        - Unless otherwise specified by user, transformation name and description are generated based on the sql query
          and user intent.
    USAGE:
        - Use when you want to create a new SQL transformation.
    EXAMPLES:
        - user_input: `Can you save me the SQL query you generated as a new transformation?`
            -> set the sql_statements to the query, and set other parameters accordingly.
            -> returns the created SQL transformation configuration if successful.
        - user_input: `Generate me an SQL transformation which [USER INTENT]`
            -> set the sql_statements to the query based on the [USER INTENT], and set other parameters accordingly.
            -> returns the created SQL transformation configuration if successful.
    """

    # Get the SQL dialect to use the correct transformation ID (Snowflake or BigQuery)
    # This can raise an exception if workspace is not set or different backend than BigQuery or Snowflake is used
    sql_dialect = await get_sql_dialect(ctx)
    transformation_id = _get_sql_transformation_id_from_sql_dialect(sql_dialect)
    LOG.info(f'SQL dialect: {sql_dialect}, using transformation ID: {transformation_id}')

    # Process the data to be stored in the transformation configuration - parameters(sql statements)
    # and storage(input and output tables)
    transformation_configuration_payload = _get_transformation_configuration(
        statements=sql_statements, transformation_name=name, output_tables=created_table_names
    )

    client = KeboolaClient.from_state(ctx.session.state)
    endpoint = (
        f'branch/{client.storage_client_sync._branch_id}/components/{transformation_id}/configs'
    )

    LOG.info(
        f'Creating new transformation configuration: {name} for component: {transformation_id}.'
    )
    # Try to create the new transformation configuration and return the new object if successful
    # or log an error and raise an exception if not
    try:
        new_raw_transformation_configuration = await client.storage_client.post(
            endpoint,
            data={
                'name': name,
                'description': description,
                'configuration': transformation_configuration_payload.model_dump(),
            },
        )

        component = await _get_component_details(client=client, component_id=transformation_id)
        new_transformation_configuration = ComponentConfiguration(
            **new_raw_transformation_configuration,
            component_id=transformation_id,
            component=component,
        )

        LOG.info(
            f'Created new transformation "{transformation_id}" with configuration id '
            f'"{new_transformation_configuration.configuration_id}".'
        )
        return new_transformation_configuration
    except Exception as e:
        LOG.exception(f'Error when creating new transformation configuration: {e}')
        raise e



async def _generate_data_app_script(
    ctx: Context, 
    name: str, 
    description: str,
    user_query: Optional[str] = None
) -> List[str]:
    """
    Generate a Streamlit script for a data app using Claude and data context.
    
    Args:
        ctx: The MCP server context
        name: The name of the data app
        description: Detailed description of what the data app should do
        user_query: Optional query from the user about what data to use
        
    Returns:
        List of script lines
    """    
    # Create a prompt for Claude that includes data context
    # TODO: Make sure libraries that need to be used but are not in the list below are added to packages
    # Use: - If any libraries are missing, add them to the packages list in config

    prompt = f"""Generate a Streamlit script for a data app named '{name}' that {description}.

User Query: {user_query if user_query else 'No specific query provided'}

Pre-installed Libraries:
- streamlit
- pandas
- numpy
- plotly
- matplotlib
- seaborn
- scikit-learn
- altair
- streamlit-aggrid
- streamlit-authenticator
- streamlit-keboola-api
- pydeck
- extra-streamlit-components

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

    # Use Claude to generate the data app
    response = await ctx.generate(prompt)
    if not response or not isinstance(response, str):
        raise ValueError("Failed to generate data app from Claude")
        
    script_lines = [
        line.strip() 
        for line in response.split('\n') 
        if line.strip() and not line.strip().startswith('```')
    ]
    
    return script_lines
    



async def create_data_app(
    ctx: Context,
    name: Annotated[
        str,
        Field(
            description='A short, descriptive name for the data app.',
        ),
    ],
    description: Annotated[
        str,
        Field(
            description='Detailed description of what the data app does and its purpose.',
        ),
    ],
    slug: Annotated[
        str,
        Field(
            description='Unique identifier for the data app (e.g., "my-data-app").',
        ),
    ],
    user_query: Annotated[
        Optional[str],
        Field(
            description='Optional query about what data to use in the data app.',
        ),
    ] = None,
    script: Annotated[
        Optional[Sequence[str]],
        Field(
            description='List of Python script lines that make up the data app. If not provided, Claude will generate a script based on the description and data context.',
        ),
    ] = None,
    size: Annotated[
        str,
        Field(
            description='Size of the data app instance (tiny, small, medium, large).',
        ),
    ] = 'tiny',
    auto_suspend_after_seconds: Annotated[
        int,
        Field(
            description='Number of seconds after which the data app will auto-suspend.',
        ),
    ] = 900,
    streamlit_config: Annotated[
        Optional[dict[str, str]],
        Field(
            description='Streamlit configuration including config.toml and other settings.',
        ),
    ] = None,
) -> Annotated[
    DataAppConfiguration,
    Field(
        description='Newly created Data App Configuration.',
    ),
]:
    """
    Creates a new data app with the specified configuration. If no script is provided,
    Claude will generate one based on the description and available data context.
    
    USAGE:
        - Use when you want to create a new data app in Keboola.
        - Use when you want Claude to generate a script based on available data.
        
    EXAMPLES:
        - user_input: "Create a data app that visualizes sales data from the sales bucket"
            - set description to explain the visualization needs
            - set user_query to specify which data to use
            - Claude will generate an appropriate script using the actual data
        - user_input: "Create a data app with this specific script"
            - provide the script directly
            - returns the created data app configuration
    """
    client = KeboolaClient.from_state(ctx.session.state)
    
    # If no script is given, use chat agent to generate one
    if not script:
        script = await _generate_data_app_script(ctx, name, description, user_query)
        LOG.info(f"Generating using agent...")
    
    # General Config
    data_app = DataApp(
        slug=slug,
        script=list(script),
        size=size,
        autoSuspendAfterSeconds=auto_suspend_after_seconds,
        streamlit=streamlit_config or { # Default keboola streamlit config
            "config.toml": "[theme]\nfont = \"sans serif\"\ntextColor = \"#222529\"\nbackgroundColor = \"#FFFFFF\"\nsecondaryBackgroundColor = \"#E6F2FF\"\nprimaryColor = \"#1F8FFF\""
        }
    )
    
    # Basic Component Configuration
    configuration = {
        'name': name,
        'description': description,
        'configuration': {
            'parameters': {
                'size': size,
                'autoSuspendAfterSeconds': auto_suspend_after_seconds,
                'dataApp': data_app.model_dump(),
                'id': slug,
                'script': script
            },
            'authorization': {
                'app_proxy': {
                    'auth_providers': [],
                    'auth_rules': [
                        {
                            'type': 'pathPrefix',
                            'value': '/',
                            'auth_required': False
                        }
                    ]
                }
            }
        }
    }
    
    # Get the data app component ID
    component_id = 'keboola.app-data-app' 
    
    endpoint = f'branch/{client.storage_client_sync._branch_id}/components/{component_id}/configs'
    
    try:
        new_raw_configuration = await client.storage_client.post(endpoint, data=configuration)
        
        # Get component details
        component = await _get_component_details(client=client, component_id=component_id)
        
        # Create and return the data app configuration
        new_configuration = DataAppConfiguration(
            **new_raw_configuration,
            component_id=component_id,
            component=component,
            data_app=data_app,
            authorization=configuration['configuration']['authorization']
        )
        
        LOG.info(f'Created new data app "{name}" with configuration id "{new_configuration.configuration_id}".')
        return new_configuration
        
    except Exception as e:
        LOG.exception(f'Error when creating new data app configuration: {e}')
        raise e

############################## End of component tools #########################################
