using System;
using System.IO;

namespace Phantom.Networking
{
    public interface IControlCredentialStore:IDisposable
    {
        bool TryLoad(string keyId,out byte[] key);
    }

    public sealed class EphemeralControlCredentialStore:IControlCredentialStore
    {
        readonly string _keyId;byte[] _key;
        public EphemeralControlCredentialStore(string keyId,byte[] key)
        {if(string.IsNullOrWhiteSpace(keyId)||key==null||key.Length<32)throw new ArgumentException("credential");_keyId=keyId;_key=(byte[])key.Clone();}
        public bool TryLoad(string keyId,out byte[] key)
        {if(_key!=null&&string.Equals(keyId,_keyId,StringComparison.Ordinal)){key=(byte[])_key.Clone();return true;}key=null;return false;}
        public void Dispose(){if(_key!=null){Array.Clear(_key,0,_key.Length);_key=null;}}
    }

    public sealed class AndroidPrivateControlCredentialStore:IControlCredentialStore
    {
        readonly string _root;
        public AndroidPrivateControlCredentialStore(string appPrivateRoot){_root=appPrivateRoot??throw new ArgumentNullException(nameof(appPrivateRoot));}
        public bool TryLoad(string keyId,out byte[] key)
        {
            key=null;if(string.IsNullOrEmpty(keyId)||keyId.IndexOfAny(new[]{'/', '\\', ':'})>=0)return false;
            var path=Path.Combine(_root,"phantom-secrets",keyId+".psk");
            try
            {
                var raw=File.ReadAllBytes(path);
                if(raw.Length==64)
                {
                    byte[] decoded;if(TryHex(raw,out decoded)){Array.Clear(raw,0,raw.Length);raw=decoded;}
                }
                if(raw.Length<32){Array.Clear(raw,0,raw.Length);return false;}
                key=raw;return true;
            }
            catch(IOException){return false;}catch(UnauthorizedAccessException){return false;}
        }
        public void Dispose(){}
        static bool TryHex(byte[] value,out byte[] decoded)
        {
            decoded=new byte[32];
            for(var i=0;i<32;i++)
            {
                var hi=Nibble(value[i*2]);var lo=Nibble(value[i*2+1]);
                if(hi<0||lo<0){Array.Clear(decoded,0,decoded.Length);decoded=null;return false;}
                decoded[i]=(byte)((hi<<4)|lo);
            }
            return true;
        }
        static int Nibble(byte b)=>b>='0'&&b<='9'?b-'0':b>='a'&&b<='f'?b-'a'+10:b>='A'&&b<='F'?b-'A'+10:-1;
    }
}
