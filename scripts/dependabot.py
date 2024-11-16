import requests
import time
import logging
from urllib.parse import quote
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv('GITHUB_USERNAME')
TOKEN = os.getenv('GITHUB_PAT')
if not TOKEN:
    raise EnvironmentError("The GITHUB_PAT environment variable is not set.")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Headers for GitHub API authentication and requests
headers = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def make_request(method, url, **kwargs):
    """Makes an HTTP request with retry logic and error handling."""
    max_retries = 5
    backoff_factor = 1  # in seconds

    for attempt in range(max_retries):
        try:
            # Merge the default headers with any headers passed in kwargs
            request_headers = headers.copy()
            if 'headers' in kwargs:
                request_headers.update(kwargs.pop('headers'))

            response = requests.request(method, url, headers=request_headers, **kwargs)

            if response.status_code == 403 and 'Retry-After' in response.headers:
                # Handle rate limiting
                retry_after = int(response.headers['Retry-After'])
                logging.warning(f"Rate limited. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code >= 500:
                # Server error, retryable
                logging.warning(f"Server error (status code {status_code}) on URL {url}. Retrying...")
                time.sleep(backoff_factor * (2 ** attempt))
                continue
            else:
                # Client error, not retryable
                logging.error(f"HTTP error (status code {status_code}) on URL {url}: {e}")
                raise
        except requests.exceptions.RequestException as e:
            # Network error, retryable
            logging.warning(f"Network error on URL {url}: {e}. Retrying...")
            time.sleep(backoff_factor * (2 ** attempt))
            continue
    else:
        logging.error(f"Failed to make request to URL {url} after {max_retries} attempts.")
        raise

def get_admin_orgs():
    """Fetches all organizations where the authenticated user is an admin or owner."""
    orgs = []
    url = 'https://api.github.com/user/memberships/orgs?per_page=100'

    while url:
        response = make_request('GET', url)
        data = response.json()
        for membership in data:
            if membership['role'] in ['admin']:
                orgs.append(membership['organization']['login'])
        # Pagination
        url = response.links.get('next', {}).get('url')
    return orgs

def get_repositories(orgs):
    """Fetches all repositories in the specified organizations where the user has admin access and are not archived."""
    repos = []
    for org in orgs:
        logging.info(f"Fetching repositories for organization: {org}")
        url = f'https://api.github.com/orgs/{org}/repos?per_page=100&type=all'

        while url:
            response = make_request('GET', url)
            data = response.json()
            for repo in data:
                is_archived = repo.get('archived', False)
                if repo.get('permissions', {}).get('admin', False) and not is_archived:
                    repos.append(repo)
                else:
                    if is_archived:
                        logging.info(f"Skipping archived repository: {repo['full_name']}")
            # Pagination
            url = response.links.get('next', {}).get('url')
    return repos

def get_pr_details(owner, repo, pull_number):
    """Fetches PR details, waiting until mergeable_state is not 'unknown'."""
    url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}'
    attempts = 0
    max_attempts = 5
    while attempts < max_attempts:
        try:
            response = make_request('GET', url)
            pr_details = response.json()
            mergeable_state = pr_details.get('mergeable_state')
            if mergeable_state != 'unknown':
                return pr_details
            else:
                logging.info(f"mergeable_state is 'unknown' for PR #{pull_number}, waiting...")
                time.sleep(2)  # wait for GitHub to calculate mergeable_state
                attempts += 1
        except Exception as e:
            logging.error(f"Error fetching PR details for PR #{pull_number}: {e}")
            return None
    # If after max_attempts it's still 'unknown', return the details anyway
    logging.warning(f"Could not determine mergeable_state for PR #{pull_number} after several attempts.")
    return pr_details

def get_branch_protection(owner, repo, branch):
    """Gets the branch protection rules for a given branch."""
    url = f'https://api.github.com/repos/{owner}/{repo}/branches/{quote(branch)}/protection'
    headers_copy = {'Accept': 'application/vnd.github.luke-cage-preview+json'}
    try:
        response = make_request('GET', url, headers=headers_copy)
        return response.json()
    except Exception as e:
        logging.error(f"Error getting branch protection for {owner}/{repo}/{branch}: {e}")
        return None

def update_branch_protection(owner, repo, branch, protection):
    """Updates the branch protection rules for a given branch."""
    url = f'https://api.github.com/repos/{owner}/{repo}/branches/{quote(branch)}/protection'
    headers_copy = {'Accept': 'application/vnd.github.luke-cage-preview+json'}
    try:
        response = make_request('PUT', url, headers=headers_copy, json=protection)
        return response
    except Exception as e:
        logging.error(f"Error updating branch protection for {owner}/{repo}/{branch}: {e}")
        return None

def update_branch_protection_to_allow_dependabot(owner, repo, branch):
    """Updates branch protection rules to allow Dependabot to bypass them."""
    protection = get_branch_protection(owner, repo, branch)
    if protection is None:
        logging.error(f"Failed to get branch protection rules for {owner}/{repo}/{branch}")
        return False

    # Flag to track if updates are made
    updated = False

    # Update 'required_pull_request_reviews' to add Dependabot to bypass allowances
    required_pull_request_reviews = protection.get('required_pull_request_reviews', {})
    if required_pull_request_reviews:
        bypass_allowances = required_pull_request_reviews.get('bypass_pull_request_allowances', {})
        apps = bypass_allowances.get('apps', [])
        if not any(app.get('slug') == 'dependabot' for app in apps):
            apps.append({'slug': 'dependabot'})
            bypass_allowances['apps'] = apps
            required_pull_request_reviews['bypass_pull_request_allowances'] = bypass_allowances
            protection['required_pull_request_reviews'] = required_pull_request_reviews
            updated = True

    # Update 'restrictions' to add Dependabot
    restrictions = protection.get('restrictions', {})
    apps = restrictions.get('apps', [])
    if not any(app.get('slug') == 'dependabot' for app in apps):
        apps.append({'slug': 'dependabot'})
        restrictions['apps'] = apps
        protection['restrictions'] = restrictions
        updated = True

    if not updated:
        logging.info(f"No updates needed for branch protection of {owner}/{repo}/{branch}.")
        return True  # No update needed

    # Prepare the protection object for the PUT request
    # Ensure all required fields are present
    protection_update = {
        'required_status_checks': protection.get('required_status_checks'),
        'enforce_admins': protection.get('enforce_admins', {}).get('enabled', False),
        'required_pull_request_reviews': protection.get('required_pull_request_reviews'),
        'restrictions': protection.get('restrictions'),
        'required_linear_history': protection.get('required_linear_history', {}).get('enabled', False),
        'allow_force_pushes': protection.get('allow_force_pushes', {}).get('enabled', False),
        'allow_deletions': protection.get('allow_deletions', {}).get('enabled', False),
    }

    # Remove keys with None values (optional)
    protection_update = {k: v for k, v in protection_update.items() if v is not None}

    # Update the branch protection
    response = update_branch_protection(owner, repo, branch, protection_update)
    if response and response.status_code in [200, 201]:
        logging.info(f"Updated branch protection for {owner}/{repo}/{branch} to allow Dependabot.")
        return True
    else:
        logging.error(f"Failed to update branch protection for {owner}/{repo}/{branch}.")
        return False

def verify_commit_signatures(owner, repo, pull_number):
    """Verifies that all commits in a pull request have valid signatures."""
    commits_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/commits"
    try:
        response = make_request('GET', commits_url)
        commits = response.json()
        unverified_commits = []
        for commit in commits:
            sha = commit['sha']
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits/{sha}"
            commit_response = make_request('GET', commit_url)
            commit_data = commit_response.json()
            verification = commit_data.get('verification', {})
            verified = verification.get('verified', False)
            reason = verification.get('reason', '')
            if not verified:
                logging.warning(f"Commit {sha} in PR #{pull_number} is not verified. Reason: {reason}.")
                unverified_commits.append((sha, reason))
            else:
                logging.info(f"Commit {sha} in PR #{pull_number} is verified.")
        if unverified_commits:
            return False, unverified_commits
        else:
            return True, None
    except Exception as e:
        logging.error(f"Error verifying commit signatures for PR #{pull_number}: {e}")
        return False, None

def check_existing_comments(owner, repo, pr_number, comment_body):
    """Checks if a specific comment already exists on the PR from the bot."""
    comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    try:
        response = make_request('GET', comments_url)
        comments = response.json()
        for comment in comments:
            if comment['user']['login'] == USERNAME and comment_body in comment['body']:
                logging.info(f"Comment already exists on PR #{pr_number}.")
                return True
        return False
    except Exception as e:
        logging.error(f"Error fetching comments for PR #{pr_number}: {e}")
        return False

def add_comment_to_pr(owner, repo, pr_number, comment_body):
    """Adds a comment to the PR."""
    comment_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    comment_data = {'body': comment_body}
    try:
        comment_response = make_request('POST', comment_url, json=comment_data)
        logging.info(f"Added comment to PR #{pr_number}: {comment_body}")
    except Exception as e:
        logging.error(f"Failed to add comment to PR #{pr_number}. Error: {e}")

def process_pull_requests(repo_owner, repo_name):
    """Finds Dependabot PRs in a repository and processes them."""
    pulls_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls?state=open&per_page=100'
    while pulls_url:
        try:
            response = make_request('GET', pulls_url)
            pull_requests = response.json()

            for pr in pull_requests:
                pr_number = pr['number']
                pr_user = pr['user']['login']
                # Check if PR is created by Dependabot
                if pr_user in ['dependabot', 'dependabot[bot]', 'app/dependabot']:
                    logging.info(f"Processing PR #{pr_number} in repository '{repo_owner}/{repo_name}'")

                    # Get PR details, ensuring 'mergeable_state' is available
                    pr_details = get_pr_details(repo_owner, repo_name, pr_number)
                    if pr_details is None:
                        logging.warning(f"Skipping PR #{pr_number} due to failure in fetching details.")
                        continue  # skip this PR

                    mergeable_state = pr_details.get('mergeable_state')
                    logging.info(f"mergeable_state for PR #{pr_number} is '{mergeable_state}'")

                    if mergeable_state == 'blocked':
                        logging.info(f"PR #{pr_number} is blocked by branch protections. Skipping.")
                        continue  # Skip this PR

                    if mergeable_state == 'behind':
                        # Add comment '@dependabot rebase' to this PR
                        rebase_comment = '@dependabot rebase'
                        # Check if the comment already exists
                        if not check_existing_comments(repo_owner, repo_name, pr_number, rebase_comment):
                            add_comment_to_pr(repo_owner, repo_name, pr_number, rebase_comment)
                        else:
                            logging.info(f"Rebase comment already exists on PR #{pr_number}.")
                        # Move to next PR
                        continue

                    if mergeable_state == 'dirty':
                        # PR has merge conflicts, add '@dependabot recreate' comment
                        recreate_comment = '@dependabot recreate'
                        # Check if the comment already exists
                        if not check_existing_comments(repo_owner, repo_name, pr_number, recreate_comment):
                            add_comment_to_pr(repo_owner, repo_name, pr_number, recreate_comment)
                        else:
                            logging.info(f"Recreate comment already exists on PR #{pr_number}.")
                        # Move to next PR
                        continue

                    # Only proceed to merge if mergeable_state is acceptable
                    acceptable_states = ['clean', 'unstable', 'has_hooks']
                    if mergeable_state not in acceptable_states:
                        logging.info(f"PR #{pr_number} is not in a mergeable state ('{mergeable_state}'). Skipping.")
                        continue  # Skip this PR

                    # Verify commit signatures
                    signatures_valid, unverified_commits = verify_commit_signatures(repo_owner, repo_name, pr_number)
                    if not signatures_valid:
                        logging.warning(f"PR #{pr_number} contains unverified commits. Skipping merge.")
                        # Construct comment body
                        comment_body = "This PR contains commits with unverified signatures. Please verify the commits before merging."
                        # Check if the comment already exists
                        if not check_existing_comments(repo_owner, repo_name, pr_number, comment_body):
                            add_comment_to_pr(repo_owner, repo_name, pr_number, comment_body)
                        else:
                            logging.info(f"Unverified commits comment already exists on PR #{pr_number}.")
                        continue  # Skip merging this PR

                    # Proceed to merge
                    sha = pr_details['head']['sha']
                    merge_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge"
                    merge_data = {'sha': sha}
                    try:
                        merge_response = make_request('PUT', merge_url, json=merge_data)
                        logging.info(f"Successfully merged PR #{pr_number} in '{repo_owner}/{repo_name}'.")
                    except requests.exceptions.HTTPError as e:
                        status_code = e.response.status_code
                        error_message = e.response.json().get('message', '')
                        if status_code == 405 or 'Branch protection' in error_message:
                            # Merge failed due to branch protection, try to update branch protection
                            logging.warning(f"Merge failed for PR #{pr_number} due to branch protection. Attempting to update branch protection rules.")
                            base_branch = pr_details['base']['ref']
                            success = update_branch_protection_to_allow_dependabot(repo_owner, repo_name, base_branch)
                            if success:
                                # Retry merging
                                try:
                                    merge_response = make_request('PUT', merge_url, json=merge_data)
                                    logging.info(f"Successfully merged PR #{pr_number} in '{repo_owner}/{repo_name}' after updating branch protection.")
                                except Exception as e:
                                    logging.error(f"Failed to merge PR #{pr_number} after updating branch protection: {e}")
                            else:
                                logging.error(f"Failed to update branch protection for '{repo_owner}/{repo_name}'. Cannot merge PR #{pr_number}.")
                        elif status_code == 409 and 'Merge conflict' in error_message:
                            logging.warning(f"PR #{pr_number} has merge conflicts. Requesting Dependabot to recreate the PR.")
                            recreate_comment = '@dependabot recreate'
                            # Check if the comment already exists
                            if not check_existing_comments(repo_owner, repo_name, pr_number, recreate_comment):
                                add_comment_to_pr(repo_owner, repo_name, pr_number, recreate_comment)
                            else:
                                logging.info(f"Recreate comment already exists on PR #{pr_number}.")
                        else:
                            logging.error(f"Failed to merge PR #{pr_number} in '{repo_owner}/{repo_name}'. Error: {e}")
                            continue
            # Pagination for pull requests
            pulls_url = response.links.get('next', {}).get('url')
        except Exception as e:
            logging.error(f"Error processing pull requests for repository '{repo_owner}/{repo_name}': {e}")
            break  # Exit the loop for this repository if there's an error

def main():
    try:
        # Get organizations where the user is an admin
        admin_orgs = get_admin_orgs()
        logging.info(f"Organizations where you are an admin: {admin_orgs}")

        # Get repositories in those organizations where you have admin access and are not archived
        repos = get_repositories(admin_orgs)

        # Process pull requests in each repository
        for repo in repos:
            repo_owner = repo['owner']['login']
            repo_name = repo['name']
            logging.info(f"Processing repository: {repo_owner}/{repo_name}")
            process_pull_requests(repo_owner, repo_name)
    except Exception as e:
        logging.error(f"An error occurred in the main process: {e}")

if __name__ == "__main__":
    main()
