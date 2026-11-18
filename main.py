from services.agent_service import AgentService

service = AgentService()

result = service.generate()

print("\nPLANS:")
print(result.plan)

print("\nTESTS:")
print(result.tests)

print("\nVALIDATION:")
print(result.validation)

print("\nDEBUG:")
print(result.debug_info)

print("\nFEATURES:")
print(result.features)