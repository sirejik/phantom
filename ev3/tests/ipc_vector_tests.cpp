// Cross-implementation check for the EV3-local IPC contract.
//
// The native network client and this C++ boundary encode the same fixed-size structures
// from config/shared/protocol/ipc-schema.json. Golden vectors carry the byte range of every
// field, so both sides prove they agree on offsets and sizes rather than only
// on the total length.
#include "phantom/json_reader.hpp"
#include "ipc_constants.hpp"
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#ifndef PHANTOM_REPO_ROOT
#define PHANTOM_REPO_ROOT "."
#endif

namespace {
namespace layout = phantom::ipc;
int failures=0;
void check(bool value,const std::string& message){if(!value){std::cerr<<"FAIL: "<<message<<"\n";++failures;}}

std::vector<unsigned char> from_hex(const std::string& text){
  std::vector<unsigned char> out;
  auto digit=[](char c)->int{
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;};
  for(std::size_t i=0;i+1<text.size();i+=2){
    const int hi=digit(text[i]),lo=digit(text[i+1]);
    if(hi<0||lo<0)return std::vector<unsigned char>();
    out.push_back((unsigned char)((hi<<4)|lo));
  }
  return out;
}

// Field offsets/sizes the generated C++ header declares, keyed the same way the
// vector file names them.
struct Expected { std::size_t offset, size; };
std::map<std::string,std::map<std::string,Expected>> generated_layout(){
  std::map<std::string,std::map<std::string,Expected>> all;
  all["ControllerRequestV1"]={
    {"magic",{layout::kControllerRequestOffsetMagic,layout::kControllerRequestSizeMagic}},
    {"ipc_version",{layout::kControllerRequestOffsetIpcVersion,layout::kControllerRequestSizeIpcVersion}},
    {"request_type",{layout::kControllerRequestOffsetRequestType,layout::kControllerRequestSizeRequestType}},
    {"reserved0",{layout::kControllerRequestOffsetReserved0,layout::kControllerRequestSizeReserved0}},
    {"controller_boot_id",{layout::kControllerRequestOffsetControllerBootId,layout::kControllerRequestSizeControllerBootId}},
    {"session_generation",{layout::kControllerRequestOffsetSessionGeneration,layout::kControllerRequestSizeSessionGeneration}},
    {"session_id",{layout::kControllerRequestOffsetSessionId,layout::kControllerRequestSizeSessionId}},
    {"role",{layout::kControllerRequestOffsetRole,layout::kControllerRequestSizeRole}},
    {"key_slot",{layout::kControllerRequestOffsetKeySlot,layout::kControllerRequestSizeKeySlot}},
    {"remote_family",{layout::kControllerRequestOffsetRemoteFamily,layout::kControllerRequestSizeRemoteFamily}},
    {"reserved1",{layout::kControllerRequestOffsetReserved1,layout::kControllerRequestSizeReserved1}},
    {"remote_ipv4_network_order",{layout::kControllerRequestOffsetRemoteIpv4NetworkOrder,layout::kControllerRequestSizeRemoteIpv4NetworkOrder}},
    {"remote_port_network_order",{layout::kControllerRequestOffsetRemotePortNetworkOrder,layout::kControllerRequestSizeRemotePortNetworkOrder}},
    {"reserved2",{layout::kControllerRequestOffsetReserved2,layout::kControllerRequestSizeReserved2}},
    {"client_nonce",{layout::kControllerRequestOffsetClientNonce,layout::kControllerRequestSizeClientNonce}},
    {"wire_sequence",{layout::kControllerRequestOffsetWireSequence,layout::kControllerRequestSizeWireSequence}},
    {"rx_monotonic_us",{layout::kControllerRequestOffsetRxMonotonicUs,layout::kControllerRequestSizeRxMonotonicUs}},
    {"command_payload",{layout::kControllerRequestOffsetCommandPayload,layout::kControllerRequestSizeCommandPayload}},
  };
  all["ControllerReplyV1"]={
    {"magic",{layout::kControllerReplyOffsetMagic,layout::kControllerReplySizeMagic}},
    {"ipc_version",{layout::kControllerReplyOffsetIpcVersion,layout::kControllerReplySizeIpcVersion}},
    {"reply_type",{layout::kControllerReplyOffsetReplyType,layout::kControllerReplySizeReplyType}},
    {"reserved0",{layout::kControllerReplyOffsetReserved0,layout::kControllerReplySizeReserved0}},
    {"controller_boot_id",{layout::kControllerReplyOffsetControllerBootId,layout::kControllerReplySizeControllerBootId}},
    {"session_generation",{layout::kControllerReplyOffsetSessionGeneration,layout::kControllerReplySizeSessionGeneration}},
    {"session_id",{layout::kControllerReplyOffsetSessionId,layout::kControllerReplySizeSessionId}},
    {"request_wire_sequence",{layout::kControllerReplyOffsetRequestWireSequence,layout::kControllerReplySizeRequestWireSequence}},
    {"result_code",{layout::kControllerReplyOffsetResultCode,layout::kControllerReplySizeResultCode}},
    {"reserved_tail",{layout::kControllerReplyOffsetReservedTail,layout::kControllerReplySizeReservedTail}},
  };
  all["ControllerTelemetrySnapshotV1"]={
    {"magic",{layout::kControllerTelemetrySnapshotOffsetMagic,layout::kControllerTelemetrySnapshotSizeMagic}},
    {"ipc_version",{layout::kControllerTelemetrySnapshotOffsetIpcVersion,layout::kControllerTelemetrySnapshotSizeIpcVersion}},
    {"reply_type",{layout::kControllerTelemetrySnapshotOffsetReplyType,layout::kControllerTelemetrySnapshotSizeReplyType}},
    {"reserved0",{layout::kControllerTelemetrySnapshotOffsetReserved0,layout::kControllerTelemetrySnapshotSizeReserved0}},
    {"controller_boot_id",{layout::kControllerTelemetrySnapshotOffsetControllerBootId,layout::kControllerTelemetrySnapshotSizeControllerBootId}},
    {"session_generation",{layout::kControllerTelemetrySnapshotOffsetSessionGeneration,layout::kControllerTelemetrySnapshotSizeSessionGeneration}},
    {"snapshot_monotonic_us",{layout::kControllerTelemetrySnapshotOffsetSnapshotMonotonicUs,layout::kControllerTelemetrySnapshotSizeSnapshotMonotonicUs}},
    {"state",{layout::kControllerTelemetrySnapshotOffsetState,layout::kControllerTelemetrySnapshotSizeState}},
    {"fault_code",{layout::kControllerTelemetrySnapshotOffsetFaultCode,layout::kControllerTelemetrySnapshotSizeFaultCode}},
    {"status_flags",{layout::kControllerTelemetrySnapshotOffsetStatusFlags,layout::kControllerTelemetrySnapshotSizeStatusFlags}},
    {"battery_mv",{layout::kControllerTelemetrySnapshotOffsetBatteryMv,layout::kControllerTelemetrySnapshotSizeBatteryMv}},
    {"grip_state",{layout::kControllerTelemetrySnapshotOffsetGripState,layout::kControllerTelemetrySnapshotSizeGripState}},
    {"loop_health_flags",{layout::kControllerTelemetrySnapshotOffsetLoopHealthFlags,layout::kControllerTelemetrySnapshotSizeLoopHealthFlags}},
    {"incident_id",{layout::kControllerTelemetrySnapshotOffsetIncidentId,layout::kControllerTelemetrySnapshotSizeIncidentId}},
    {"q_actual_rad",{layout::kControllerTelemetrySnapshotOffsetQActualRad,layout::kControllerTelemetrySnapshotSizeQActualRad}},
    {"q_speed_rad_s",{layout::kControllerTelemetrySnapshotOffsetQSpeedRadS,layout::kControllerTelemetrySnapshotSizeQSpeedRadS}},
    {"grip_actual",{layout::kControllerTelemetrySnapshotOffsetGripActual,layout::kControllerTelemetrySnapshotSizeGripActual}},
    {"reserved_tail",{layout::kControllerTelemetrySnapshotOffsetReservedTail,layout::kControllerTelemetrySnapshotSizeReservedTail}},
  };
  return all;
}

std::map<std::string,std::size_t> generated_lengths(){
  return {{"ControllerRequestV1",layout::kControllerRequestBytes},
          {"ControllerReplyV1",layout::kControllerReplyBytes},
          {"ControllerTelemetrySnapshotV1",layout::kControllerTelemetrySnapshotBytes}};
}
}

int main(){
  const std::string path=std::string(PHANTOM_REPO_ROOT)+"/protocol/golden_vectors/ipc_v1.json";
  std::ifstream stream(path,std::ios::binary);
  std::ostringstream buffer;buffer<<stream.rdbuf();
  const std::string text=buffer.str();
  check(!text.empty(),"IPC golden vectors are readable: "+path);
  if(text.empty())return 1;

  phantom::JsonValue root;std::string error;
  check(phantom::parse_json(text,root,error,4194304),"IPC golden vectors parse: "+error);
  const phantom::JsonValue* vectors=root.find("vectors");
  check(vectors&&vectors->kind==phantom::JsonValue::Kind::Array&&!vectors->items.empty(),"IPC vectors present");
  if(!vectors)return 1;

  const auto expected_layout=generated_layout();
  const auto expected_lengths=generated_lengths();
  std::size_t verified_fields=0;

  for(const phantom::JsonValue& vector:vectors->items){
    const phantom::JsonValue* name=vector.find("name");
    const phantom::JsonValue* length=vector.find("length");
    const phantom::JsonValue* bytes_hex=vector.find("bytes_hex");
    const phantom::JsonValue* fields=vector.find("fields");
    check(name&&length&&bytes_hex&&fields,"vector shape");
    if(!name||!length||!bytes_hex||!fields)continue;

    const std::string message=name->text;
    const auto declared=expected_lengths.find(message);
    check(declared!=expected_lengths.end(),"generated C++ header declares "+message);
    if(declared==expected_lengths.end())continue;
    check((std::size_t)length->number==declared->second,message+": length disagrees with the generated C++ constant");

    const std::vector<unsigned char> encoded=from_hex(bytes_hex->text);
    check(encoded.size()==declared->second,message+": vector byte length");

    const auto& message_layout=expected_layout.at(message);
    for(const phantom::JsonValue& field:fields->items){
      const phantom::JsonValue* field_name=field.find("name");
      const phantom::JsonValue* offset=field.find("offset");
      const phantom::JsonValue* size=field.find("size");
      const phantom::JsonValue* hex=field.find("hex");
      check(field_name&&offset&&size&&hex,"field shape");
      if(!field_name||!offset||!size||!hex)continue;
      const auto declared_field=message_layout.find(field_name->text);
      check(declared_field!=message_layout.end(),message+": generated header is missing field "+field_name->text);
      if(declared_field==message_layout.end())continue;
      check(declared_field->second.offset==(std::size_t)offset->number,
            message+"."+field_name->text+": offset disagrees between the schema vector and the generated C++ header");
      check(declared_field->second.size==(std::size_t)size->number,
            message+"."+field_name->text+": size disagrees between the schema vector and the generated C++ header");
      const std::vector<unsigned char> field_bytes=from_hex(hex->text);
      check(field_bytes.size()==declared_field->second.size,message+"."+field_name->text+": vector field length");
      if(field_bytes.size()==declared_field->second.size&&encoded.size()>=declared_field->second.offset+field_bytes.size()){
        check(std::equal(field_bytes.begin(),field_bytes.end(),encoded.begin()+declared_field->second.offset),
              message+"."+field_name->text+": bytes at the generated offset do not match the vector");
      }
      ++verified_fields;
    }
  }
  check(verified_fields>=40,"expected every IPC field to be cross-checked");
  if(failures)return 1;
  std::cout<<"EV3 IPC golden vector tests PASS ("<<verified_fields<<" fields cross-checked)\n";
  return 0;
}
