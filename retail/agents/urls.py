from retail.agents.push.routers import urlpatterns as push_urlpatterns
from retail.agents.assign.routers import urlpatterns as assign_urlpatterns
from retail.agents.webhooks.routers import urlpatterns as webhooks_urlpatterns

urlpatterns = assign_urlpatterns + push_urlpatterns + webhooks_urlpatterns
