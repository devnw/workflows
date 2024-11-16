import requests
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv('GITHUB_USERNAME')
# Pull the GitHub Personal Access Token from an environment variable
TOKEN = os.getenv('GITHUB_PAT')
if not TOKEN:
    raise EnvironmentError("The GITHUB_PAT environment variable is not set.")


# Define the labels you want to add/update
# Each label is a dictionary with 'name', 'color', and 'description'
labels_to_set = [
    {
        'name': 'automerge',
        'color': 'eab676',
        'description': "label for automerge action"
    },
]

# Headers for GitHub API authentication and requests
headers = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def get_repositories():
    """Fetches all repositories where the authenticated user has admin rights."""
    repos = []
    url = 'https://api.github.com/user/repos?per_page=100&affiliation=owner,organization_member'

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        for repo in data:
            if repo.get('permissions', {}).get('admin', False):
                repos.append(repo)
        # GitHub API pagination
        url = response.links.get('next', {}).get('url')

    return repos

def update_labels(repo_owner, repo_name):
    """Updates or creates labels for a given repository."""
    # Get existing labels in the repository
    labels_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/labels'
    response = requests.get(labels_url, headers=headers)
    response.raise_for_status()
    existing_labels = {label['name']: label for label in response.json()}

    for label in labels_to_set:
        label_name = label['name']
        label_data = {
            'name': label_name,
            'color': label['color'],
            'description': label.get('description', '')
        }

        if label_name in existing_labels:
            # Update the existing label
            update_url = f"{labels_url}/{label_name}"
            resp = requests.patch(update_url, headers=headers, json=label_data)
            if resp.status_code == 200:
                print(f"Updated label '{label_name}' in repository '{repo_owner}/{repo_name}'.")
            else:
                print(f"Failed to update label '{label_name}' in repository '{repo_owner}/{repo_name}'. Error: {resp.content}")
        else:
            # Create a new label
            resp = requests.post(labels_url, headers=headers, json=label_data)
            if resp.status_code == 201:
                print(f"Created label '{label_name}' in repository '{repo_owner}/{repo_name}'.")
            else:
                print(f"Failed to create label '{label_name}' in repository '{repo_owner}/{repo_name}'. Error: {resp.content}")

def main():
    repos = get_repositories()
    for repo in repos:
        repo_owner = repo['owner']['login']
        repo_name = repo['name']
        print(f"\\nProcessing repository: {repo_owner}/{repo_name}")
        update_labels(repo_owner, repo_name)

if __name__ == "__main__":
    main()
