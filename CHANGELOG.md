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