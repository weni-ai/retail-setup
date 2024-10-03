class BuildExternalGlobalsUsecase:
    def __init__(self, integrations_service, flows_service):
        self.integrations_service = integrations_service
        self.flows_service = flows_service

    def execute(self, features: list[dict], user_email: str, project_uuid: str) -> list[dict]:
        # Fetch data from the services, handling cases where data might be None
        integrations_data = self.integrations_service.get_vtex_integration_detail(project_uuid)
        flows_data = self.flows_service.get_user_api_token(user_email, project_uuid)

        for feature in features:
            globals_to_remove = []
            
            # Check and mark globals for removal based on integrations data if available
            if integrations_data:
                if "x_vtex_api_appkey" in feature["globals"] and integrations_data.get("app_key"):
                    globals_to_remove.append("x_vtex_api_appkey")
                if "x_vtex_api_apptoken" in feature["globals"] and integrations_data.get("app_token"):
                    globals_to_remove.append("x_vtex_api_apptoken")
                if "url_api_vtex" in feature["globals"] and integrations_data.get("domain"):
                    globals_to_remove.append("url_api_vtex")

            # Check and mark globals for removal based on flows data if available
            if flows_data:
                if "user_api_token" in feature["globals"] and flows_data.get("api_token"):
                    globals_to_remove.append("user_api_token")

            # Remove the marked globals
            feature["globals"] = [
                g for g in feature["globals"] if g not in globals_to_remove
            ]
        
        return features
