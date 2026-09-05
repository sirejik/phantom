using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Phantom.Networking;
using Phantom.Networking.Generated;

internal static class GoldenVectorInterop
{
    static byte[] Hex(string value){var bytes=new byte[value.Length/2];for(var i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;}
    public static int Main(string[] args)
    {
        if(args.Length!=1)throw new ArgumentException("golden vector JSON path required");
        var text=File.ReadAllText(args[0]);
        var matches=Regex.Matches(text,"\\\"name\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"[\\s\\S]*?\\\"hmac_key_hex\\\"\\s*:\\s*\\\"([0-9a-f]+)\\\"[\\s\\S]*?\\\"datagram_hex\\\"\\s*:\\s*\\\"([0-9a-f]+)\\\"");
        if(matches.Count!=21)throw new Exception("expected 21 golden vectors, got "+matches.Count);
        foreach(Match match in matches)
        {
            var name=match.Groups[1].Value;var key=Hex(match.Groups[2].Value);var bytes=Hex(match.Groups[3].Value);
            DecodedDatagram decoded;if(!ProtocolCodec.TryDecode(bytes,key,out decoded))throw new Exception("Quest codec rejected golden "+name);
            var encoded=ProtocolCodec.Encode(decoded.Header.MessageType,decoded.Payload,key,decoded.Header.SessionId,
                                              decoded.Header.ControllerBootId,decoded.Header.Sequence,decoded.Header.SenderMonotonicUs);
            if(!encoded.SequenceEqual(bytes))throw new Exception("Quest round-trip changed bytes for "+name);
            if(name=="HELLO_ACK"){HelloAckPacket value;if(!ServerProtocol.TryDecodeHelloAck(decoded,out value)||value.BuildId.Length!=64)throw new Exception("HELLO_ACK semantic decode");}
            if(name=="TELEMETRY"){TelemetryPacket value;if(!ServerProtocol.TryDecodeTelemetry(decoded,out value)||value.BuildId.Length!=64)throw new Exception("TELEMETRY semantic decode");}
        }
        Console.WriteLine("PASS: Quest decoded and byte-round-tripped all 21 EV3/Python golden vectors");return 0;
    }
}
