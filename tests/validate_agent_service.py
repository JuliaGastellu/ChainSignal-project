import asyncio
import json
from services.agent_service import AgentService

async def main():
    service = AgentService()
    test_wallet = "0x0000000000000000000000000000000000000000"
    
    print(f"--- Testing Stream for {test_wallet} ---")
    async for event in service.run_pipeline_stream(test_wallet):
        print(f"Stream Event: {event.strip()}")
        
    print(f"\n--- Testing Core Report for {test_wallet} ---")
    try:
        # For burn address, it should return the special case logic
        # Note: In our current implementation, _run_pipeline_generator yields events 
        # for burn address but might not yield final_report_data unless we added it.
        # Let's check.
        report = await service.run_pipeline_core(test_wallet)
        print(f"Report: {json.dumps(report, indent=2)}")
    except Exception as e:
        print(f"Report Error (Expected if no report data): {e}")

    # Test a real-looking (but likely empty) wallet to see full pipeline (mocked/Etherscan)
    real_test_wallet = "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae" # ETH Developer wallet
    print(f"\n--- Testing Stream for {real_test_wallet} ---")
    # We only take first 5 events to avoid long wait
    count = 0
    async for event in service.run_pipeline_stream(real_test_wallet):
        print(f"Stream Event: {event.strip()}")
        count += 1
        if count >= 5: break

if __name__ == "__main__":
    asyncio.run(main())
