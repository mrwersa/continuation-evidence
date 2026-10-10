"""Keep remote command output separate from gcloud resource formatting."""


def command(args, account):
    remote = tuple(args[:2]) in (("compute", "ssh"), ("compute", "scp"))
    if remote and any(a == "--format" or a.startswith("--format=") for a in args):
        raise ValueError("Remote commands must not use resource output formatting")
    result = ["gcloud", *args, "--project=your-gcp-project", "--account=" + account, "--quiet"]
    if not remote:
        result.append("--format=json")
    return result
