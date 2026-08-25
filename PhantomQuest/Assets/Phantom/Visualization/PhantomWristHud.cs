using System.Text;
using Phantom.Tracking;
using UnityEngine;
using UnityEngine.UI;

namespace Phantom.Visualization
{
    public sealed class PhantomWristHud : MonoBehaviour
    {
        const float DistanceMeters=1.05f;
        const float HorizontalOffsetMeters=0f;
        const float VerticalOffsetMeters=-.04f;
        const int WrapColumns=52;
        const float PanelWidthMeters=.82f;
        const float PanelHeightMeters=.66f;
        const float CanvasWidth=1024f;
        const float CanvasHeight=824f;

        Text _text;
        RectTransform _panel;
        Camera _camera;
        bool _cameraReported;
        string _content="PHANTOM: ЗАПУСК";
        string _renderedContent;

        public string Content
        {
            get=>_content;
            set=>_content=value??"";
        }

        void Awake()
        {
            var panelObject=new GameObject("PhantomHeadLockedWorldCanvas",typeof(RectTransform),typeof(Canvas));
            panelObject.layer=5;
            _panel=panelObject.GetComponent<RectTransform>();
            _panel.SetParent(transform,false);
            _panel.sizeDelta=new Vector2(CanvasWidth,CanvasHeight);
            _panel.localScale=Vector3.one*(PanelWidthMeters/CanvasWidth);

            var canvas=panelObject.GetComponent<Canvas>();
            canvas.renderMode=RenderMode.WorldSpace;
            canvas.sortingOrder=100;

            var backgroundObject=new GameObject("PhantomHudBackground",typeof(RectTransform),typeof(CanvasRenderer),typeof(Image));
            backgroundObject.layer=5;
            var backgroundRect=backgroundObject.GetComponent<RectTransform>();
            backgroundRect.SetParent(_panel,false);
            Stretch(backgroundRect,Vector2.zero);
            backgroundObject.GetComponent<Image>().color=new Color(.015f,.025f,.035f,.56f);

            var textObject=new GameObject("PhantomHudRussianText",typeof(RectTransform),typeof(CanvasRenderer),typeof(Text));
            textObject.layer=5;
            var textRect=textObject.GetComponent<RectTransform>();
            textRect.SetParent(_panel,false);
            Stretch(textRect,new Vector2(38f,30f));
            _text=textObject.GetComponent<Text>();
            _text.font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _text.fontSize=31;
            _text.resizeTextForBestFit=false;
            _text.alignment=TextAnchor.UpperCenter;
            _text.horizontalOverflow=HorizontalWrapMode.Wrap;
            _text.verticalOverflow=VerticalWrapMode.Truncate;
            _text.color=new Color(.15f,1f,1f,1f);

        }

        public void SetTracking(TrackingFrame frame)
        {
            if(_panel&&!_panel.gameObject.activeSelf)_panel.gameObject.SetActive(true);
        }

        void LateUpdate()
        {
            if(!_text)return;
            if(_renderedContent!=_content)
            {
                _renderedContent=_content;
                _text.text=Wrap(_renderedContent,WrapColumns);
            }

            _camera=Camera.main;
            if(!_camera)return;
            if(_panel.parent!=_camera.transform)
            {
                _panel.SetParent(_camera.transform,false);
                _panel.localPosition=new Vector3(HorizontalOffsetMeters,VerticalOffsetMeters,DistanceMeters);
                _panel.localRotation=Quaternion.identity;
                _panel.localScale=Vector3.one*(PanelWidthMeters/CanvasWidth);
                _cameraReported=false;
            }
            if(!_cameraReported)
            {
                _cameraReported=true;
                Debug.Log($"PHANTOM HUD eye_buffer_head_locked center_m={HorizontalOffsetMeters:F2} distance_m={DistanceMeters:F2} size_m={PanelWidthMeters:F2}x{PanelHeightMeters:F2} font_px={_text.fontSize} camera={_camera.name}");
            }
        }

        static void Stretch(RectTransform value,Vector2 margin)
        {
            value.anchorMin=Vector2.zero;
            value.anchorMax=Vector2.one;
            value.offsetMin=margin;
            value.offsetMax=-margin;
            value.localRotation=Quaternion.identity;
            value.localScale=Vector3.one;
        }

        static string Wrap(string value,int columns)
        {
            if(string.IsNullOrEmpty(value))return value;
            var output=new StringBuilder(value.Length+32);
            var lines=value.Replace("\r","").Split('\n');
            for(var lineIndex=0;lineIndex<lines.Length;lineIndex++)
            {
                if(lineIndex>0)output.Append('\n');
                var column=0;
                var words=lines[lineIndex].Split(new[]{' '},System.StringSplitOptions.RemoveEmptyEntries);
                foreach(var word in words)
                {
                    if(column>0&&column+1+word.Length>columns){output.Append('\n');column=0;}
                    else if(column>0){output.Append(' ');column++;}
                    output.Append(word);column+=word.Length;
                }
            }
            return output.ToString();
        }
    }
}
