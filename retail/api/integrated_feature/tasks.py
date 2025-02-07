from celery import shared_task
from retail.api.usecases.install_actions_usecase import InstallActions
from retail.features.models import IntegratedFeature, Feature


@shared_task
def execute_install_actions_task(
    integrated_feature_uuid,
    feature_uuid,
    data,
):
    """
    Executes install actions asynchronously for the integrated feature.
    """
    try:
        integrated_feature = IntegratedFeature.objects.get(uuid=integrated_feature_uuid)
        feature = Feature.objects.get(uuid=feature_uuid)
        install_actions = InstallActions()

        install_actions.execute(
            integrated_feature=integrated_feature,
            feature=feature,
            data=data,
        )

        print(f"Install actions executed successfully for feature {feature.uuid}")
    except Exception as e:
        print(f"Error executing install actions: {str(e)}")
