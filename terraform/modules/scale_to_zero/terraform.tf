terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      configuration_aliases = [
        aws.target
      ]

    }
    archive = {
      source = "hashicorp/archive"
    }
  }
}
