"""
Script para popular country_phone_code em todos os agentes integrados ativos.

Uso:
    python manage.py shell < scripts/populate_country_phone_codes.py
"""

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
)

fetch_usecase = FetchCountryPhoneCodeUseCase()

agents = IntegratedAgent.objects.filter(is_active=True).select_related("project")
total = agents.count()

print(f"Found {total} active integrated agents")

success = 0
skip = 0
error = 0

for agent in agents:
    project = agent.project

    if not project.vtex_account:
        print(f"  SKIP agent={agent.uuid} - no vtex_account")
        skip += 1
        continue

    if agent.config.get("country_phone_code"):
        print(f"  SKIP agent={agent.uuid} - already has phone code")
        skip += 1
        continue

    try:
        phone_code = fetch_usecase.execute(project)

        if not phone_code:
            print(f"  WARN agent={agent.uuid} - could not fetch phone code")
            error += 1
            continue

        agent.config["country_phone_code"] = phone_code
        agent.save(update_fields=["config"])

        print(f"  OK agent={agent.uuid} phone_code={phone_code}")
        success += 1

    except Exception as e:
        print(f"  ERROR agent={agent.uuid} - {e}")
        error += 1

print(f"\nTotal: {total} | Success: {success} | Skip: {skip} | Error: {error}")
