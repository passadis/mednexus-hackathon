"""Check the actual partition key path on the Cosmos container."""
import asyncio, sys
sys.path.insert(0, "src")

from azure.cosmos.aio import CosmosClient
from mednexus.config import settings


async def main():
    client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
    db = client.get_database_client(settings.cosmos_database)
    container = db.get_container_client(settings.cosmos_container)
    props = await container.read()
    pk_path = props["partitionKey"]["paths"]
    print(f"Container: {settings.cosmos_container}")
    print(f"Partition key paths: {pk_path}")

    # Try reading P003 with different partition key values
    from azure.cosmos import exceptions

    # Attempt 1: partition_key = "P003"
    try:
        doc = await container.read_item(item="P003", partition_key="P003")
        print(f"\nread_item(partition_key='P003') -> FOUND: id={doc['id']}")
    except exceptions.CosmosResourceNotFoundError:
        print(f"\nread_item(partition_key='P003') -> NOT FOUND")
    except Exception as e:
        print(f"\nread_item(partition_key='P003') -> ERROR: {e}")

    # Attempt 2: query without partition key
    try:
        items = []
        async for doc in container.query_items(
            query="SELECT * FROM c WHERE c.id = 'P003'",
        ):
            items.append(doc)
        print(f"query(id='P003') -> Found {len(items)} docs")
        if items:
            print(f"  partition_key field: {items[0].get('partition_key', 'N/A')}")
            print(f"  patient.patient_id: {items[0].get('patient', {}).get('patient_id', 'N/A')}")
    except Exception as e:
        print(f"query -> ERROR: {e}")

    await client.close()


asyncio.run(main())
