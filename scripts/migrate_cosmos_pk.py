"""Migrate existing Cosmos docs to have a top-level patient_id field (partition key)."""
import asyncio, sys
sys.path.insert(0, "src")

from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions
from mednexus.config import settings


async def main():
    client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
    db = client.get_database_client(settings.cosmos_database)
    container = db.get_container_client(settings.cosmos_container)

    # 1. Find all docs (cross-partition)
    print("Finding all documents ...")
    docs = []
    async for doc in container.query_items(
        query="SELECT * FROM c",
    ):
        docs.append(doc)
    print(f"  Found {len(docs)} documents")

    for doc in docs:
        pid = doc["id"]
        has_patient_id = "patient_id" in doc
        print(f"\n  {pid}: top-level patient_id={'YES' if has_patient_id else 'MISSING'}")

        if not has_patient_id:
            # Delete old doc (stored under undefined partition key)
            print(f"    Deleting old doc (undefined partition) ...")
            try:
                # Try with None/empty partition key
                from azure.cosmos.documents import NonePartitionKeyValue
                await container.delete_item(item=pid, partition_key=NonePartitionKeyValue)
                print(f"    Deleted (NonePartitionKeyValue)")
            except Exception as e1:
                try:
                    await container.delete_item(item=pid, partition_key=pid)
                    print(f"    Deleted (partition_key={pid})")
                except Exception as e2:
                    print(f"    Could not delete: {e1} / {e2}")
                    continue

            # Re-insert with patient_id at top level
            doc["patient_id"] = pid
            # Remove Cosmos system fields
            for key in ["_rid", "_self", "_etag", "_attachments", "_ts"]:
                doc.pop(key, None)
            print(f"    Re-inserting with patient_id={pid} ...")
            await container.upsert_item(doc)
            print(f"    Done!")

    # Verify
    print("\n\nVerification — point-read P003:")
    try:
        doc = await container.read_item(item="P003", partition_key="P003")
        print(f"  SUCCESS: id={doc['id']}, patient_id={doc.get('patient_id')}")
    except exceptions.CosmosResourceNotFoundError:
        print(f"  STILL NOT FOUND")
    except Exception as e:
        print(f"  ERROR: {e}")

    await client.close()
    print("\nMigration complete!")


asyncio.run(main())
