/* Fixed bounded wire format, matched by geck_mcp/console.py. No engine layouts. */
#pragma once
#pragma pack(push,1)
typedef struct {
    char magic[8], id[33], context[33], build[65];
    uint32_t pid;
    uint64_t started;
    uint32_t epoch;
    uint64_t deadline;
    uint32_t prefix;
    char command[513];
    uint32_t verify_kind, verify_form;
    char variable[65];
    double expected;
    uint32_t query_index;
    char subject_plugin[65], subject_hash[65];
    uint32_t subject_local, query_kind, teleport;
    char next_context[33];
} ConsoleRequest;
#pragma pack(pop)
_Static_assert(sizeof(ConsoleRequest)==940,"console request ABI");
