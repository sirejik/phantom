using System;
using System.IO;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine;
#endif

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
            key=null;if(!ValidKeyId(keyId))return false;
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using(var store=new AndroidJavaClass("dev.phantom.security.PhantomCredentialStore"))
                {
                    using(var unity=new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                    using(var activity=unity.GetStatic<AndroidJavaObject>("currentActivity"))
                        key=store.CallStatic<byte[]>("load",activity,keyId);
                    if(key!=null&&key.Length>=32)return true;
                    if(key!=null)Array.Clear(key,0,key.Length);key=null;return false;
                }
            }
            catch(AndroidJavaException){key=null;return false;}
#else
            // Host-only fallback used by editor tests. Android production never
            // reads a plaintext credential file and fails closed if Keystore fails.
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
#endif
        }
        public bool Provision(string keyId,byte[] key)
        {
            if(!ValidKeyId(keyId)||key==null||key.Length<32)return false;
#if UNITY_ANDROID && !UNITY_EDITOR
            var copy=(byte[])key.Clone();
            try
            {
                using(var store=new AndroidJavaClass("dev.phantom.security.PhantomCredentialStore"))
                using(var unity=new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using(var activity=unity.GetStatic<AndroidJavaObject>("currentActivity"))
                    return store.CallStatic<bool>("provision",activity,keyId,copy);
            }
            catch(AndroidJavaException){return false;}
            finally{Array.Clear(copy,0,copy.Length);}
#else
            return false;
#endif
        }
        public void Dispose(){}
        static bool ValidKeyId(string value)
        {
            if(string.IsNullOrEmpty(value)||value.Length>64)return false;
            for(var i=0;i<value.Length;i++)
            {var c=value[i];if(!(c>='a'&&c<='z'||c>='A'&&c<='Z'||c>='0'&&c<='9'||c=='-'||c=='_'||c=='.'))return false;}
            return true;
        }
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
