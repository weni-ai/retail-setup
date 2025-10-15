# 3.19.2

## *Feature*
  - feat: add configuration to ignore empty carts for specific projects

# 3.19.1

## *Feature*
  - feat: add logs to broadcast service

# 3.19.0

## *Feature*
  - feat: ensure unique UUID for projects and improve message consumption logging
  - feat: add parent_agent_uuid field to IntegratedAgent model and update order status use case logic
  - feat: add Celery Beat schedule for cleaning up old carts
  - refactor: fetch_templates_from_user

## *Fix*
  - fix: Use direct imports in template model

# 3.18.6

## *Feature*
  - feat: setup elastic apm
  - feat: clears cache after updating integrated agent
  - feat: add cors config

# 3.18.5

## *Feature*
  - feat: Implement generic proxy functionality for VTEX IO API requests

## *Fix*
  - fix: add serializer_class to ProjectViewSet to resolver swagger error

## *Fix*
  - fix: Use direct imports in template model

# 3.18.4

## *Fix*
  - fix: update flows_channel_uuid field to allow null and blank values

## *Feature*
  - feat: add logging for request exceptions and response errors in RequestClient

# 3.18.3

## *Fix*
  - fix: remove purchase status verification and add JWT authentication to purchase event

# 3.18.2

## *Fix*
  - fix: update order_id to order_form_id and add more logs in purchase event

# 3.18.1

## *Feature*
  - feat: optimize webhook

## *Fix*
  - fix: disable templates triggering

# 3.18.0

## *Refactor*
  - refactor: agents app

# 3.17.0

## *Feature*
  - feat: implement project permission
  - feat: proxy for permissions

# 3.16.0

## *Feature*
  - feat: add retry method to rule_generator
  - feat: permissions per project

# 3.15.0

## *Feature*
  - feat: add JWT token generation and integrate it into LambdaHandler
  - feat: change authorization from aws to jwt

# 3.14.0

## *Feature*
  - feat: handle non preapproved
  - feat: add unit tests for VTEX module, repositories, and CAPI use cases
  - feat: add phone number restriction for abandoned cart
  - feat: register events using weni-datalake-sdk

# 3.13.0

## *Feature*
  - feat: add 13-digits hash as active agent lambda function name
  - feat: add validation for examples and push agent is now atomic

## *Fix*
  - fix: send header image in broadcast

# 3.12.1

## *Fix*
  - hotfix: duplicated integrated agents

# 3.12.0

## *Feature*
  - feat: support image in template header

# 3.11.2

## *Fix*
  - fix: send template name in custom rule

# 3.11.1

## *Feature*
  - feat: add logger error when creating lambda fails

# 3.11.0

## *Feature*
  - feat: add lambda logs
  - feat: cache integrated agent in webhook

## *Fix*
  - fix: prevent duplicate notifications for abandoned carts

# 3.10.2

## *Feature*
  - feat: implement abandoned cart notification cooldown and duplicate prevention

# 3.10.1

## *Feature*
  - feat: verify if cart items were purchased recently

## *Fix*
  - fix: change CAPI authorization and handling purchase event

# 3.10.0

## *Feature*
  - feat: add JWT authentication for inter-module communication
  - feat: new metadata format

## *Fix*
  - fix: sentry logger error of type project with account not found
  - fix: update template with parameters

# 3.9.2

## *Fix*
  - fix: remove global prompt

# 3.9.1

## *Fix*
  - fix: better logs

# 3.9.0

## *Feature*
  - feature: global rule

# 3.8.2

## *Fix*
  - fix: temporarily disable OrderFormTrackingView due to authorization issues

# 3.8.1

## *Feature*
  - feat: add __str__ to ORMs

## *Fix*
  - fix: sentry error in retrieving template name without current version

# 3.8.0

## *Feature*
  - feat: add WhatsApp click-ID support to Cart model and implement tracking functionality

# 3.7.1

## *Fix*
  - fix: templates with variables were not using examples

# 3.7.0

## *Feature*
  - feat: query params to filter templates from integrated agent

## *Fix*
  - fix: update custom templat not finding category

# 3.6.0

## *Feature*
  - feat: custom templates creation

# 3.5.0

## *Feature*
  - feat: refactor agent webhook usecase and add lambda status handle

## *Fix*
  - fix: check current version before triggering template

# 3.4.0

## *Feature*
  - feat: implement fetch_template_metrics functionality

# 3.3.0

## *Feature*
  - feat: add missing agents usecases tests
  - feat: async notify integrations
  - feat: CI tests & coverage

## *Fix*
  - fix: removed button never was set to none

# 3.2.15

## *Feature*
  - feat: add lambda timeout variable

# 3.2.14

## *Feature*
  - feat: add Swagger documentation for Gallery API

## *Fix*
  - fix: update order endpoint URL in VtexIOClient

# 3.2.13

## *Fix*
  - fix: enhance logging and handle missing integrated features in cart a

# 3.2.12

## *Feature*
  - feat: implement rejection handling for template creation tasks
  - feat: add indexes to Project model for uuid and vtex_account fields
  - feat: filter features to return only abandoned cart for new integrations

## *Fix*
  - fix: improve logging for missing integrated features in cart and orde

# 3.2.11

## *Feature*
  - Feature/redirect update events webhook to agent
  - feat: add config field to IntegratedAgent and implement phone restric…
  - feat: implement cache clearing for unassigning agents and add logging
  - feat: block specific UUID in agent webhook processing and enhance log…
  - feat: add caching for project domain retrieval and implement cache cl…

## *Fix*
  - fix: edit template button not working
  - fix: add pending templates to ignore list
  - fix: saving none button in metadata
  - fix: pass button to integrations
  - refactor: remove unused fields from order status webhook payload and …
  - fix: verify current version before remove template
  - refactor: simplify error messages in order status update use case and…
  - fix: remove slug correctly
  - refactor: simplify error handling in order status update use case and…
  - fix: check project is not None to update order status
  - fix: pass ignored templates to webhook
  - fix: improve logging for missing contact_urn and handle missing integ…
  - fix: enhance logging in agent webhook and order status update use cases

# 3.0.1

## *Fix*
  - fix: remove unique together between agent name and project
  - fix: update order status webhook to use specific celery queue
  - fix: project object uuid and add cache to order status retrieval
  - fix: update project UUID handling in cart abandonment
  - fix: template shows last version status

## *Feature*
  - feat: pass language to meta
  - feat: add soft delete to template
  - feat: sending the project in lambda invoke
  - feat: add get account identifier and add base vtex usecase
  - feat: add percent of contacts to trigger webhook
  - feat: add proxy order detail
  - feat: handler button edit in update template
  - feat: feat: add VtexAccountLookupView

# 3.0.0

## *Fix*
  - fix: template changing agent
  - fix: update template header and footer

## *Feature*
  - feat: serialize missing fields
  - feat: slug in preapproved

# 2.0.0

## *Fix*
  - fix: update payload handling in AgentWebhookUseCase to read from response directly

## *Feature*
  - feat: add channel uuid to integrated agent
  - feat: pass credentials to webhook
  - feat: implement whatsapp broadcast message build to integrated agent
  - feat: agent slug
  - feature: serialize credentials
  - feat: pre approved templates extra fields

# 1.10.0

## *Change*
  - fix: remove lambda arn from integrated agent
  - feat: apis to list and retrieve assigned agent
  - feat: add credentials to the push and assign agent endpoint

# 1.9.1

## *Change*
  - hotfix: push agent breaking

# 1.9.0

## *Change*
  - fix: create async template with task
  - feat: list and get agents
  - refactor: move IntegrationsService from template to retail.services.integrations
  - feat: assign agent
  - feat: unassign agent
  - feat: Add script to generate local .env configuration file
  - fix: Push agent lambda exception and meta
  - fix: push agent permissions
  - feat: agent webhook

# 1.8.0

## *Change*
  - feat: template app

# 1.7.1

## *Change*
  - fix: adjust lambda authentication

# 1.7.0

## *Add*
  - feat: add nexus agents
  - feat: add route to return IO orders by params and add aws request auth

# 1.6.6

## *Change*
  - fix: remove logger error spamming sentry

# 1.6.5

## *Change*
  - fix: add task_id to check_templates_synchronization task

# 1.6.4

## *Change*
  - fix: encode project_uuid from object to string

# 1.6.3

## *Change*
  - fix: change autorization key to X-Weni-Auth

# 1.6.2

## *Change*
  - fix: remove static vtex workspace

# 1.6.1

## *Change*
  - fix: Integrated features showing cross projects

# 1.6.0

## *Add*
  - feat: add pre-commit to project
  - Feature/vtex project app consumer
  - feat: create code action and use run code action to send notifications
  - feat: dynamic vtex workspace
  - feat: add delete integrated feature usecase and delete code action linked

## *Change*
  - fix: remove authentication by params from vtex requets

# 1.5.0

## *Add*
  - feat: add webhook to sync template status

# 1.4.2

## *Change*
  - fix: save and send client locale to notification message
  - fix: send client name to abandoned cart notification

## *Add*
  - feat: add config field to project and add viewset to set store type

# 1.4.1

## *Change*
  - fix: add slash to the cart link
  - fix: move project uuid from client to payload

# 1.4.0

## *Add*
  - feat: applying black to the project
  - feat: add task to sync templates from integrated features
  - feat: edit existing vtex projects and displays error with multiple projects
  - feat: add dynamic template names
  - feat: add order status restriction rules
  - adding category in return from feature and integrated_feature
  - feat: implement message builder and send order status notifications
  - Feature/app integrated feature\
  - Feature/get phone number from order
  - Feature/order status webhook
  - Feature/schedule abandoned cart notification based on settings
  - feature: create order status templates on integrate feature with inst…
  - feat: add utm_source to order form related to the abandoned cart
  - Feature/update integrated feature config

## *Change*
  - fix: use babel to translate templates infos
  - fix: get integration_settings value before validation
  - fix: add abandoned cart countdown to settings
  - fix: abandoned cart notification with domain
  - fix: change static button urls to dynamic
  - fix: rename order form field names

# 1.3.4

## *HotFix*
  - add username when user are created

# 1.3.3

## *HotFix*
  - add celery configuration
  - add fix to none globals in feature version
  - add sentry

# 1.3.2

## *Hotfix*
  - add default value to vtex_account

# 1.3.1

## *Hotfix*
  - fix vtex_account field on Project model

# 1.3.0

## *Add*
  - adding the methods and objects to make the request to vtex app
  - adding abandoned cart create template and send for user

# 1.2.5

## *Change*
  - fix: adjust the value of the global api_token key

# 1.0.1

## *Change*
  - setting the disclaimer and documentation url fields as not required to create a feature

# 1.0.0

## *Add*
  - keycloak
  - event driven with wenieda library
  - integrate feature by api with frontend
  - update integreated feature
  - delete integration
  - list features
  - list integrated features
  - create project with eda
  - send message to wenichats, flows, agent builder with data to integrate a feature
  - get globals by integrations and flows with a client
