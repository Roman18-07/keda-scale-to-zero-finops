data "aws_eks_cluster" "apps" {
  provider = aws.target

  name = local.kubernetesClusterName
}

# Inspired by https://marcincuber.medium.com/amazon-eks-with-oidc-provider-iam-roles-for-kubernetes-services-accounts-59015d15cb0c
data "aws_iam_openid_connect_provider" "apps_eks_openid" {
  provider = aws.target

  url = data.aws_eks_cluster.apps.identity.0.oidc.0.issuer
}
