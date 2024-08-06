from django.contrib import admin


from retail.projects.models import Project
from retail.features.models import Feature


class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "organization_name", "uuid")

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        if change:
            self.change_form_template = "projects_change_form.html"

        return super().render_change_form(request, context, add, change, form_url, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if extra_context is None:
            extra_context = {}

        project = Project.objects.get(id=object_id)

        extra_context["integrated_features"] = project.integrated_features.all()
        extra_context["features"] = Feature.objects.exclude(
            integrated_features__project=project
        )
        return super().change_view(request, object_id, form_url, extra_context)


admin.site.register(Project, ProjectAdmin)
