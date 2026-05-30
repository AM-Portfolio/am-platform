# Declarative user profile — required for custom attributes (e.g. settings JSON).
# Without this, Keycloak accepts user PUT 204 but silently drops unknown attributes.

resource "keycloak_realm_user_profile" "am_realm_user_profile" {
  realm_id = keycloak_realm.am_realm.id

  group {
    name                 = "user-metadata"
    display_header       = "User metadata"
    display_description  = "Attributes, which refer to user metadata"
  }

  attribute {
    name         = "username"
    display_name = "$${username}"
    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }
  }

  attribute {
    name         = "email"
    display_name = "$${email}"
    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }
  }

  attribute {
    name         = "firstName"
    display_name = "$${firstName}"
    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }
  }

  attribute {
    name         = "lastName"
    display_name = "$${lastName}"
    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }
  }

  attribute {
    name         = "settings"
    display_name = "User Settings"
    group        = "user-metadata"
    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }
  }
}
