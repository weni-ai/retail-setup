from retail.features.models import Feature
from typing import Dict, Any


class PopulateDefaultsUseCase:
    """
    Use case to populate default values from a feature's configuration.
    This allows for setting default global values and potentially other configurations
    as specified within the feature's config field.
    """

    def execute(
        self, feature: Feature, globals_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes the population of default values for globals, updating
        only with keys that have defined default values in the feature config.

        Args:
            feature (Feature): The feature object containing configuration.
            globals_values (dict): Current global values to be populated with defaults.

        Returns:
            dict: Updated globals_values containing defaults for applicable keys.
        """
        globals_values = self._populate_globals(feature, globals_values)
        return globals_values

    def _populate_globals(
        self, feature: Feature, globals_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Populates globals with default values from the feature config,
        only for keys present in default settings.

        Args:
            feature (Feature): The feature object containing configuration.
            globals_values (dict): Current global values.

        Returns:
            dict: Dictionary with globals populated only with default keys found in feature config.
        """
        # Load default values for 'globals' from the feature's `config` field
        default_globals = (
            feature.config.get("vtex_config", {})
            .get("default_params", {})
            .get("globals_values", {})
        )

        # Create a dictionary with only the keys present in `default_globals`
        populated_globals = {
            key: default_value
            for key, default_value in default_globals.items()
            if key in globals_values
            or globals_values.setdefault(key, default_value) is not None
        }

        return populated_globals
