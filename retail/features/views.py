import json

from django.template.response import TemplateResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from retail.projects.models import Project
from retail.features.integrated_feature_eda import IntegratedFeatureEDA
from .models import Feature, IntegratedFeature, FeatureVersion
from .forms import IntegrateFeatureForm


@login_required
def integrate_feature_view(request, project_uuid, feature_uuid):
    project = get_object_or_404(Project, uuid=project_uuid)
    feature = get_object_or_404(Feature, uuid=feature_uuid)

    last_version = feature.last_version

    if request.method == "POST":
        form = IntegrateFeatureForm(request.POST, feature=feature)
        if form.is_valid():
            integrated_feature = form.save(commit=False)
            integrated_feature.project = project
            integrated_feature.user = request.user
            integrated_feature.save()

            sectors_data = []
            for sector in integrated_feature.sectors:
                sectors_data.append(
                    {
                        "name": sector.get("name", ""),
                        "tags": sector.get("tags", ""),
                        "service_limit": 4,
                        "working_hours": {"init": "08:00", "close": "18:00"},
                        "queues": sector.get("queues", []),
                    }
                )

            body = {
                "definition": integrated_feature.feature_version.definition,
                "user_email": integrated_feature.user.email,
                "project_uuid": str(integrated_feature.project.uuid),
                "parameters": integrated_feature.globals_values,
                "feature_version": str(integrated_feature.feature_version.uuid),
                "feature_uuid": str(integrated_feature.feature.uuid),
                "sectors": sectors_data,
                "action": {
                    "name": integrated_feature.feature_version.action_name,
                    "prompt": integrated_feature.feature_version.action_prompt,
                    "root_flow_uuid": integrated_feature.feature_version.action_base_flow_uuid,
                },
            }
            IntegratedFeatureEDA().publisher(
                body=body, exchange="integrated-feature.topic"
            )
            print(f"message send `integrated feature` - body: {body}")

            redirect_url = reverse("admin:projects_project_change", args=[project.id])
            return redirect(redirect_url)
    else:
        form = IntegrateFeatureForm(feature=feature)
        form.initial["feature_version"] = last_version
    flow_base = last_version.get_flows_base()
    context = {
        "title": f"Integrar {feature}",
        "feature": feature,
        "form": form,
        "versions": {},
        "versions_sectors": {},
        "actions": {},
        "last_version_params": last_version.globals_values,
        "version_sectors": last_version.sectors,
        "action_base_flow": flow_base,
        "button_title": "Concluir integração",
    }

    for version in feature.versions.all():
        context["versions"][str(version.uuid)] = version.globals_values
        context["versions_sectors"][str(version.uuid)] = version.sectors
        context["actions"][str(version.uuid)] = version.get_flows_base()

    return TemplateResponse(request, "integrate_feature.html", context)


@login_required
def update_feature_view(request, project_uuid, integrated_feature_uuid):
    project = get_object_or_404(Project, uuid=project_uuid)
    integrated_feature = get_object_or_404(
        IntegratedFeature, uuid=integrated_feature_uuid
    )
    feature = integrated_feature.feature
    last_version = feature.last_version
    flow_base = last_version.get_flows_base()

    if request.method == "POST":
        form = IntegrateFeatureForm(request.POST, feature=feature)
        if form.is_valid():
            integrated_feature.user = request.user
            integrated_feature.sectors = request.POST["sectors"]
            integrated_feature.globals_values = request.POST["globals_values"]
            integrated_feature.project = project
            integrated_feature.feature_version = FeatureVersion.objects.get(
                uuid=request.POST["feature_version"]
            )
            integrated_feature.save()
            sectors_data = []
            for sector in json.loads(integrated_feature.sectors):
                sectors_data.append(
                    {
                        "name": sector.get("name", ""),
                        "tags": sector.get("tags", ""),
                        "service_limit": 4,
                        "working_hours": {"init": "08:00", "close": "18:00"},
                        "queues": sector.get("queues", []),
                    }
                )
            body = {
                "definition": integrated_feature.feature_version.definition,
                "user_email": integrated_feature.user.email,
                "project_uuid": str(integrated_feature.project.uuid),
                "parameters": integrated_feature.globals_values,
                "feature_version": str(integrated_feature.feature_version.uuid),
                "feature_uuid": str(integrated_feature.feature.uuid),
                "sectors": sectors_data,
                "action": {
                    "name": integrated_feature.feature_version.action_name,
                    "prompt": integrated_feature.feature_version.action_prompt,
                    "root_flow_uuid": integrated_feature.feature_version.action_base_flow_uuid,
                },
            }
            IntegratedFeatureEDA().publisher(
                body=body, exchange="update-integrated-feature.topic"
            )
            print(f"message send `update integrated feature` - body: {body}")
        redirect_url = reverse("admin:projects_project_change", args=[project.id])
        return redirect(redirect_url)

    else:
        form = IntegrateFeatureForm(feature=feature)
        form.initial["feature_version"] = last_version

    context = {
        "title": f"Atualizar {integrated_feature.feature}",
        "feature": feature,
        "form": form,
        "versions": {},
        "versions_sectors": {},
        "actions": {},
        "last_version_params": last_version.globals_values,
        "version_sectors": last_version.sectors,
        "action_base_flow": flow_base,
        "button_title": "Concluir atualização",
    }
    for version in feature.versions.all():
        context["versions"][str(version.uuid)] = version.globals_values
        context["versions_sectors"][str(version.uuid)] = version.sectors
        context["actions"][str(version.uuid)] = version.get_flows_base()

    return TemplateResponse(request, "integrate_feature.html", context)


@login_required
def remove_feature_view(request, project_uuid, integrated_feature_uuid):
    project = get_object_or_404(Project, uuid=project_uuid)
    integrated_feature = get_object_or_404(
        IntegratedFeature, uuid=integrated_feature_uuid
    )
    body = {
        "project_uuid": str(project.uuid),
        "feature_version": str(integrated_feature.feature_version.uuid),
        "feature_uuid": str(integrated_feature.feature.uuid),
        "user_email": request.user.email,
    }
    print(f"body: {body}")
    IntegratedFeatureEDA().publisher(body=body, exchange="removed-feature.topic")
    integrated_feature.delete()
    redirect_url = reverse("admin:projects_project_change", args=[project.id])
    return redirect(redirect_url)

    # feature = integrated_feature.feature
    # feature_version = integrated_feature.feature_version
