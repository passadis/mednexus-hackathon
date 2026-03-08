"""Quick Cosmos DB connectivity test."""
import asyncio
import sys
sys.path.insert(0, "src")

from mednexus.services.cosmos_client import get_cosmos_manager


async def main():
    m = get_cosmos_manager()
    try:
        # 1. Test write
        print("1) Creating test patient 'PTEST' ...")
        ctx = await m.create_context("PTEST", "Test Patient")
        print(f"   Created: {ctx.patient.patient_id} / {ctx.patient.name}")

        # 2. Test point-read
        print("2) Reading back 'PTEST' ...")
        readback = await m.get_context("PTEST")
        if readback:
            print(f"   Found: {readback.patient.patient_id} / {readback.patient.name}")
        else:
            print("   NOT FOUND — write may have silently failed")

        # 3. Test list (cross-partition query)
        print("3) Listing all contexts ...")
        contexts = await m.list_contexts(limit=10)
        print(f"   Found {len(contexts)} patients")
        for c in contexts:
            print(f"    - {c.patient.patient_id}: {c.patient.name}")

        # 4. Cleanup test patient
        print("4) Deleting 'PTEST' ...")
        await m.delete_context("PTEST")
        print("   Deleted.")

        # 5. Check for P003
        print("5) Checking P003 ...")
        p003 = await m.get_context("P003")
        if p003:
            print(f"   Found: {p003.patient.patient_id} / {p003.patient.name}")
        else:
            print("   NOT FOUND — needs re-seeding")

    except Exception as e:
        import traceback
        print(f"ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await m.close()


if __name__ == "__main__":
    asyncio.run(main())
