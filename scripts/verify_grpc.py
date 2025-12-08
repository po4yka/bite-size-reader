import asyncio
import os
import sys

import grpc

# Add project root to path
sys.path.append(os.getcwd())

from app.protos import processing_pb2, processing_pb2_grpc


async def main():
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = processing_pb2_grpc.ProcessingServiceStub(channel)

        url = "https://example.com"
        print(f"Submitting URL: {url}")

        request = processing_pb2.SubmitUrlRequest(url=url, language="en", force_refresh=True)

        try:
            async for update in stub.SubmitUrl(request):
                status_name = processing_pb2.ProcessingStatus.Name(update.status)
                stage_name = processing_pb2.ProcessingStage.Name(update.stage)
                print(
                    f"Update: ID={update.request_id} Status={status_name} Stage={stage_name} Progress={update.progress:.2f} Msg='{update.message}'"
                )

                if update.error:
                    print(f"Error: {update.error}")
        except grpc.RpcError as e:
            print(f"RPC Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
