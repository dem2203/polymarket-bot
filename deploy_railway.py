"""Railway deploy script — set env vars and trigger deploy."""
import requests
import json

TOKEN = "0da7546d-50a8-442c-a4a0-119c958ca2f8"
PROJECT_ID = "b13fb787-60eb-4c37-9dc9-3489350e5db8"
ENV_ID = "36a3bdf6-3419-40bb-b911-8673a2da503e"
SERVICE_ID = "c80485ce-bf0c-4dc1-9701-da83b4d77179"

URL = "https://backboard.railway.app/graphql/v2"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def gql(query):
    resp = requests.post(URL, headers=HEADERS, json={"query": query})
    data = resp.json()
    if "errors" in data:
        print(f"ERROR: {data['errors']}")
    else:
        print(f"OK: {json.dumps(data.get('data', {}), indent=2)}")
    return data


def set_variables():
    """Set non-secret env vars."""
    variables = {
        "DRY_RUN": "true",
        "STARTING_BALANCE": "50",
        "MAX_KELLY_FRACTION": "0.06",
        "KELLY_MULTIPLIER": "0.5",
        "MISPRICING_THRESHOLD": "0.08",
        "STOP_LOSS_PCT": "0.20",
        "TAKE_PROFIT_PCT": "0.25",
        "DAILY_LOSS_LIMIT": "25",
        "SURVIVAL_BALANCE": "5.0",
        "MAX_TOTAL_EXPOSURE": "100",
        "SCAN_INTERVAL": "600",
        "MIN_VOLUME": "10000",
        "MIN_LIQUIDITY": "1000",
        "MAX_MARKETS_PER_SCAN": "1000",
        "AI_MODEL": "claude-haiku-4-5-20241022",
        "AI_MAX_TOKENS": "512",
    }

    vars_json = json.dumps(variables)
    query = (
        'mutation { variableCollectionUpsert(input: {'
        f'projectId: "{PROJECT_ID}", '
        f'environmentId: "{ENV_ID}", '
        f'serviceId: "{SERVICE_ID}", '
        f'variables: {vars_json}'
        '}) }'
    )
    print("Setting environment variables...")
    return gql(query)


def trigger_deploy():
    """Trigger a deployment from latest commit."""
    query = (
        'mutation { serviceInstanceRedeploy('
        f'environmentId: "{ENV_ID}", '
        f'serviceId: "{SERVICE_ID}"'
        ') }'
    )
    print("\nTriggering deployment...")
    return gql(query)


if __name__ == "__main__":
    # 1. Set env vars
    result = set_variables()

    # 2. Trigger deploy
    result2 = trigger_deploy()

    print("\n" + "=" * 50)
    print("DONE! Check Railway dashboard:")
    print(f"https://railway.com/project/{PROJECT_ID}")
    print("=" * 50)
    print("\n⚠️  Hatırlatma: ANTHROPIC_API_KEY, POLYMARKET_PRIVATE_KEY,")
    print("   TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID değerlerini")
    print("   Railway dashboard > Variables'dan manuel ekleyin!")
