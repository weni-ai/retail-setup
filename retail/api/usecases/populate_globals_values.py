"""
PopulateGlobalsValuesUsecase is responsible for filling in specific global keys 
in the globals_values dictionary using data fetched from external services.

Attributes:
    integrations_service: Service used to fetch data related to VTEX integrations.
    flows_service: Service used to fetch user API tokens from the flows system.
"""


class PopulateGlobalsValuesUsecase:
    def __init__(self, integrations_service, flows_service):
        self.integrations_service = integrations_service
        self.flows_service = flows_service

    def execute(self, globals_values: dict, user_email: str, project_uuid: str) -> dict:
        """
        Fill in the keys of globals_values using the appropriate services.
        Only the following keys are manipulated:
        - x_vtex_api_appkey
        - x_vtex_api_apptoken
        - url_api_vtex
        - api_token (from flows, mapped to 'token')
        """
        filled_globals_values = globals_values.copy()

        # Handle the keys related to the integrations service
        integration_data = self.integrations_service.get_vtex_integration_detail(
            project_uuid
        )
        if integration_data:
            if "url_api_vtex" in globals_values:
                filled_globals_values["url_api_vtex"] = integration_data.get(
                    "domain", globals_values["url_api_vtex"]
                )
            if "x_vtex_api_appkey" in globals_values:
                filled_globals_values["x_vtex_api_appkey"] = integration_data.get(
                    "app_key", globals_values["x_vtex_api_appkey"]
                )
            if "x_vtex_api_apptoken" in globals_values:
                filled_globals_values["x_vtex_api_apptoken"] = integration_data.get(
                    "app_token", globals_values["x_vtex_api_apptoken"]
                )

        # Handle the key related to the flows service (api_token)
        flow_data = self.flows_service.get_user_api_token(user_email, project_uuid)
        if flow_data:
            if "api_token" in globals_values:
                filled_globals_values["api_token"] = flow_data.get(
                    "api_token", globals_values["api_token"]
                )

        return filled_globals_values
