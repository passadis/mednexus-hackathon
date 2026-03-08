"""Delete and recreate the patients container, then re-upsert test data."""
import asyncio, sys
sys.path.insert(0, "src")

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from mednexus.config import settings
from mednexus.models.clinical_context import ClinicalContext, PatientDemographics


PATIENTS = [
    ("P001", "John Mitchell"),
    ("P002", "Emma Rodriguez"),
    ("P003", "Robert Chen"),
]


async def main():
    client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
    db = await client.create_database_if_not_exists(settings.cosmos_database)

    # 1. Delete old container
    print(f"Deleting container '{settings.cosmos_container}' ...")
    try:
        await db.delete_container(settings.cosmos_container)
        print("  Deleted.")
    except Exception as e:
        print(f"  Not found or error: {e}")

    # 2. Recreate with correct partition key path
    print(f"Creating container with partition key /patient_id ...")
    container = await db.create_container_if_not_exists(
        id=settings.cosmos_container,
        partition_key=PartitionKey(path="/patient_id"),
    )
    print("  Created.")

    # 3. Insert patients with correct schema
    for pid, name in PATIENTS:
        ctx = ClinicalContext(
            id=pid,
            partition_key=pid,
            patient=PatientDemographics(patient_id=pid, name=name),
        )
        doc = ctx.to_cosmos_doc()
        doc["patient_id"] = pid  # Top-level PK field
        await container.upsert_item(doc)
        print(f"  Upserted {pid}: {name}")

    # 4. Verify point-reads
    print("\nVerification:")
    for pid, name in PATIENTS:
        doc = await container.read_item(item=pid, partition_key=pid)
        print(f"  read_item({pid}) -> OK: {doc.get('patient', {}).get('name', '?')}")

    await client.close()
    print("\nDone! Container recreated with 3 patients.")


asyncio.run(main())
