import asyncio
import json
from services.agent_service import AgentService

async def test_service_stream():
    service = AgentService()
    wallet = "0x3Bd196Ab866cB99251AcC4b62722cF0BdC5A4c13"
    print(f"Testing AgentService.run_pipeline_stream for {wallet}...")
    
    count = 0
    async for event in service.run_pipeline_stream(wallet):
        # Extract data from 'data: {...}'
        if event.startswith("data: "):
            data = json.loads(event[6:])
            print(f"[{data.get('paso')}] {data.get('estado')}: {data.get('detalle')}")
            count += 1
    
    print(f"\nTotal events received: {count}")
    if count > 0:
        print("SUCCESS: Service produced events.")
    else:
        print("FAILURE: No events produced.")

if __name__ == "__main__":
    asyncio.run(test_service_stream())
