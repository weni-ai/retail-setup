from django.template.response import TemplateResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse


from retail.projects.models import Project
from .models import Feature, IntegratedFeature
from .forms import IntegrateFeatureForm


@login_required
def integrate_feature_view(request, project_uuid, feature_uuid):
    project = get_object_or_404(Project, uuid=project_uuid)
    feature = get_object_or_404(Feature, uuid=feature_uuid)

    if request.method == "POST":
        form = IntegrateFeatureForm(request.POST, feature=feature)
        if form.is_valid():
            integrated_feature = form.save(commit=False)
            integrated_feature.project = project
            integrated_feature.user = request.user
            integrated_feature.save()

            redirect_url = reverse("admin:projects_project_change", args=[project.id])

            return redirect(redirect_url)
    else:
        form = IntegrateFeatureForm(feature=feature)

    context = {"title": f"Integrar {feature}", "feature": feature, "form": form}

    return TemplateResponse(request, "integrate_feature.html", context)


@login_required
def update_feature_view(request, project_uuid, integrated_feature_uuid):
    project = get_object_or_404(Project, uuid=project_uuid)
    integrated_feature = get_object_or_404(
        IntegratedFeature, uuid=integrated_feature_uuid
    )
    feature = integrated_feature.feature

    if request.method == "POST":
        pass

    else:
        form = IntegrateFeatureForm(feature=feature)
        form.initial["parameters"] = integrated_feature.parameters
        form.initial["feature_version"] = integrated_feature.feature_version

    context = {
        "title": f"Atualizar {integrated_feature.feature}",
        "feature": feature,
        "form": form,
    }

    return TemplateResponse(request, "update_feature.html", context)
