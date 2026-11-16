terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.7.1"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.4"
    }
  }

  backend "s3" {}
}
