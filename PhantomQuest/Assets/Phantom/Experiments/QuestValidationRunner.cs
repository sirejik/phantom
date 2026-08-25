using System;
using System.Globalization;
using Phantom.Kinematics;
using Phantom.Logging;
using Phantom.RobotLocalization;
using Phantom.Room;
using Phantom.Tracking;
using UnityEngine;

namespace Phantom.Experiments
{
    public enum QuestTestId
    {
        Q0_Environment, Q1_Multimodal, Q2_Grasp, Q3_WristVsPalm, Q4_RoomStability,
        Q5_FixedQr, Q6_QrMatrix, Q7_MarkerRig, Q8_UserShoulderFit, Q9_Drift,
        Q10_TrackingPauseLoss, Q11_UdpSimulator, Q12_FullStartupDryRun,
        Q13_QrAbsoluteJointReference, Q14_QrEncoderCrossCheck
    }

    public sealed class QuestValidationRunner : MonoBehaviour
    {
        static readonly string[] Q0Phases=
        {
            "Убедитесь, что видна реальная комната, текст, руки и лучи. Подождите 5 секунд и нажмите X.",
            "Медленно поворачивайте голову и двигайте обеими руками 10 секунд. Затем нажмите X.",
            "Откройте системное меню Meta, вернитесь в PHANTOM и после восстановления изображения нажмите X.",
            "Стойте спокойно 10 секунд. Оцените дрожание виртуального слоя и нажмите X."
        };

        static readonly string[] Q1Phases=
        {
            "Держите левый Touch Plus. Правая рука свободна и видна. Когда ОБА=ДА, нажмите X.",
            "60 секунд держите контроллер и правую руку перед собой. Затем нажмите X.",
            "10 раз нажмите и отпустите левый Grip. Затем нажмите X.",
            "5 раз нажмите левый курок, не удерживая его. Затем нажмите X.",
            "Нажмите Y 3 раза. Кнопка X уже проверяется подтверждением каждого шага; затем нажмите X.",
            "Медленно переместите правую руку влево, вправо, вверх и вниз. Нажмите X.",
            "Двигайте левым контроллером, удерживая правую руку неподвижно. Нажмите X.",
            "Откройте меню Meta, вернитесь в PHANTOM и дождитесь ОБА=ДА. Нажмите X.",
            "Спрячьте правую руку на 1–2 секунды и верните. После восстановления нажмите X.",
            "Спрячьте левый контроллер на 1–2 секунды и верните. После ОБА=ДА нажмите X."
        };

        static readonly string[] GraspTokens={"OPEN","25","50","75","FIST","OPEN_RETURN"};
        static readonly string[] GraspLabels={"ОТКРЫТА","СЖАТЬ НА 25%","СЖАТЬ НА 50%","СЖАТЬ НА 75%","КУЛАК","СНОВА ОТКРЫТА"};

        static readonly string[] Q3Phases=
        {
            "Зафиксируйте правое запястье в удобном положении. Держите ладонь открытой 5 секунд и нажмите X.",
            "Не двигая предплечьем, 10 раз поверните кисть влево/вправо примерно на 60–90°. Нажмите X.",
            "Сохраняя запястье на месте, 10 раз выполните ОТКРЫТА→КУЛАК→ОТКРЫТА. Нажмите X.",
            "Снова держите открытую ладонь неподвижно 5 секунд и нажмите X."
        };

        static readonly string[] Q4Phases=
        {
            "Стойте неподвижно и смотрите вперёд 5 секунд, затем нажмите X.",
            "Поверните голову влево, вправо, вверх и вниз, каждый раз возвращаясь в центр. Нажмите X.",
            "Шагните на 0,5 м вперёд, ждите 3 секунды, вернитесь и снова ждите 3 секунды. Нажмите X.",
            "Откройте меню Meta на 5 секунд, вернитесь, ждите 5 секунд и нажмите X.",
            "Удерживайте кнопку Meta для переноса центра, ждите 5 секунд и нажмите X.",
            "Стойте неподвижно 10 секунд. Если комната стабильна, нажмите X."
        };

        static readonly string[] Q10Phases=
        {
            "В нормальном состоянии нажмите и отпустите левый Grip. Убедитесь, что движение останавливается. Нажмите X.",
            "Удерживая Grip, спрячьте правую руку на 1–2 секунды. Верните руку, но Grip сначала отпустите. Нажмите X.",
            "Удерживая Grip, спрячьте левый контроллер на 1–2 секунды. Верните и отпустите Grip. Нажмите X.",
            "Откройте системное меню Meta, вернитесь и сначала отпустите Grip. Нажмите X.",
            "Дождитесь сетевого отключения от PC. После восстановления сначала отпустите Grip. Нажмите X.",
            "Снова зажмите Grip только после полного восстановления. Убедитесь, что скачка цели нет, и нажмите X."
        };

        static readonly string[] Q11Phases=
        {
            "PC-сценарий NORMAL: двигайте рукой 10 секунд, отпустите Grip и нажмите X.",
            "PC-сценарий LATENCY100: двигайте рукой 10 секунд, отпустите Grip и нажмите X.",
            "PC-сценарий LOSS5: двигайте рукой 15 секунд, отпустите Grip и нажмите X.",
            "PC-сценарий BURST_LOSS: двигайте рукой 15 секунд, отпустите Grip и нажмите X.",
            "PC-сценарий STALE: дождитесь защитной реакции, отпустите Grip и нажмите X.",
            "PC-сценарий WRONG_SESSION: дождитесь защитной реакции, отпустите Grip и нажмите X.",
            "PC-сценарий DISCONNECT: дождитесь отключения и восстановления, отпустите Grip и нажмите X.",
            "PC-сценарий FAULT: дождитесь состояния ОШИБКА, не зажимайте Grip и нажмите X."
        };

        static readonly string[] Q12Phases=
        {
            "Холодный запуск выполнен. Убедитесь, что реальная комната распознана, и нажмите X.",
            "Убедитесь, что SIM=ОК и рукопожатие с PC завершено. Нажмите X.",
            "Покажите неподвижный комплект меток робота до завершения калибровки. Нажмите X.",
            "Запустите калибровку пользователя кнопкой Y и выполните три большие дуги прямой рукой.",
            "Завершите калибровку кнопкой Y. После принятия результата нажмите X.",
            "Проверьте виртуальный призрак цели и безопасную позу. Нажмите X.",
            "Дождитесь состояния ГОТОВО или УДЕРЖАНИЕ. Нажмите X.",
            "Зажмите левый Grip и убедитесь, что появилось СЛЕЖЕНИЕ. Нажмите X.",
            "Плавно перемещайте правую руку 10 секунд. Нажмите X.",
            "Отпустите Grip: движение должно остановиться. Нажмите X.",
            "Снова зажмите Grip: цель не должна прыгнуть. Нажмите X.",
            "Спрячьте правую руку на 1–2 секунды: ожидается БЕЗОПАСНАЯ ОСТАНОВКА.",
            "Верните руку, но сначала отпустите Grip. После восстановления нажмите X.",
            "Снова зажмите Grip, проверьте плавное продолжение и нажмите X."
        };

        MetaQuestTrackingSource _tracking;
        QuestJsonlLogger _logger;
        QuestTestId _test;
        bool _running,_sequenceComplete;
        int _samples,_phaseStep,_phaseValidSamples;
        TrackingFrame _last;
        bool _lastX,_lastY,_lastTrigger;
        float _triggerPressedAt=-1f;
        int _q5ValidSamples,_q5StableSamples;
        string _q5Payload;
        bool _q5PayloadLocked,_q5PreviousValid;
        QrMarkerObservation _q5Previous;

        const int Q5RequiredStableSamples=30;
        const int Q6RequiredValidSamplesPerCell=20;
        const int Q7RequiredValidSamplesPerScan=10;

        public string Summary=>$"{TestTitle(_test)} | {CurrentPhase} | {(_running?"ЗАПУЩЕН":"ОСТАНОВЛЕН")} | отсчётов={_samples} | запуск={_logger?.RunId??"—"}";
        public string Instructions=>InstructionsForCurrentPhase();

        public string HudText
        {
            get
            {
                var status=_running?"ЗАПУЩЕН":"ОСТАНОВЛЕН";
                var progress=$"ШАГ {Math.Min(_phaseStep+1,PhaseCount(_test))}/{PhaseCount(_test)}";
            var controls=_running?(_sequenceComplete?"СЦЕНАРИЙ ЗАВЕРШЁН. УДЕРЖИВАЙТЕ КУРОК 2 С = СОХРАНИТЬ":"ВЫПОЛНИТЕ ШАГ; X = ПОДТВЕРДИТЬ; КУРОК 2 С = СТОП"):"X = ПРЕДЫДУЩИЙ; Y = СЛЕДУЮЩИЙ; КУРОК = СТАРТ";
                var extra="";
                if(_test==QuestTestId.Q5_FixedQr)
                    extra=_phaseStep==1?$"\nСТАБИЛЬНОСТЬ {_q5StableSamples}/{Q5RequiredStableSamples}; QR: {_q5Payload??"ожидание"}":_phaseStep==2?$"\nЗАПИСАНО {_q5ValidSamples}/500; QR: {_q5Payload??"ожидание"}":"";
                else if(_test==QuestTestId.Q6_QrMatrix&&_running)
                    extra=$"\nВАЛИДНЫХ КАДРОВ {_phaseValidSamples}/{Q6RequiredValidSamplesPerCell}; QR: {_q5Payload??"ожидание"}";
                else if(_test==QuestTestId.Q7_MarkerRig&&_running)
                    extra=$"\nСТАБИЛЬНЫХ КАДРОВ КОМПЛЕКТА {_phaseValidSamples}/{Q7RequiredValidSamplesPerScan}";
                return $"{TestTitle(_test)} — {status}\nЦЕЛЬ: {TestPurpose(_test)}\n{progress}\n{InstructionsForCurrentPhase()}{extra}\n{controls}";
            }
        }

        void Awake(){_tracking=GetComponent<MetaQuestTrackingSource>();}

        void Update()
        {
            if(_tracking==null||!_tracking.TryGetFrame(out _last))return;
            var xRise=_last.LeftController.X&&!_lastX;
            var yRise=_last.LeftController.Y&&!_lastY;
            var trigger=_last.LeftController.Trigger>.75f;
            var triggerRise=trigger&&!_lastTrigger;
            if(triggerRise)_triggerPressedAt=Time.unscaledTime;
            else if(!trigger)_triggerPressedAt=-1f;
            _lastX=_last.LeftController.X;_lastY=_last.LeftController.Y;_lastTrigger=trigger;

            if(!_running)
            {
                if(xRise)_test=(QuestTestId)Math.Max(0,(int)_test-1);
                if(yRise)_test=(QuestTestId)Math.Min(14,(int)_test+1);
                if(triggerRise)StartRun(_test);
                return;
            }

            if(trigger&&_triggerPressedAt>=0f&&Time.unscaledTime-_triggerPressedAt>=2f)
            {
                _triggerPressedAt=-1f;
                StopRun();
                return;
            }
            _samples++;
            if(xRise&&!_sequenceComplete)
            {
                if(_test==QuestTestId.Q5_FixedQr&&_phaseStep==0)AdvanceQ5ToWarmup();
                else if(_test==QuestTestId.Q6_QrMatrix)AdvanceQrMatrixPhase();
                else if(_test==QuestTestId.Q7_MarkerRig)AdvanceMarkerRigPhase();
                else if(_test!=QuestTestId.Q5_FixedQr)AdvanceGuidedPhase();
            }
            if((_samples%10)!=0)return;
            if(_test==QuestTestId.Q4_RoomStability)CaptureRoomSample();
            else if(_test==QuestTestId.Q5_FixedQr)CaptureQ5Sample();
            else if(_test==QuestTestId.Q6_QrMatrix)CaptureQrMatrixSample();
            else if(_test==QuestTestId.Q7_MarkerRig)CaptureMarkerRigSample();
            else _logger.Log(_test.ToString(),"tracking_sample",CurrentPhase,"",JsonUtility.ToJson(_last));
        }

        void CaptureRoomSample()
        {
            var room=RoomReferenceRegistry.Current;
            _logger.Log(_test.ToString(),"tracking_sample",CurrentPhase,"",JsonUtility.ToJson(new RoomTrackingSample
            {
                tracking=_last,room_ready=room?.IsReady==true,room_status=room?.StatusReason??"ссылка на комнату недоступна",floor_origin=room?.FloorOrigin??Vec3.Zero
            }));
        }

        void AdvanceQ5ToWarmup(){ConfirmCurrentPhase();_phaseStep=1;StartCurrentPhase();}

        void CaptureQ5Sample()
        {
            var valid=TryCaptureQr(out var qr,out var status);
            if(_phaseStep==1)
            {
                if(valid&&_q5PreviousValid&&QrPositionDelta(qr,_q5Previous)<=.01&&QrAngleDegrees(qr,_q5Previous)<=3.0)_q5StableSamples++;
                else _q5StableSamples=0;
                _q5Previous=qr;_q5PreviousValid=valid;
            }
            else if(_phaseStep==2&&valid)_q5ValidSamples++;
            LogQrSample(qr,status);
            if(_phaseStep==1&&_q5StableSamples>=Q5RequiredStableSamples)
            {
                _logger.Log(_test.ToString(),"warmup_complete",CurrentPhase,"",$"{{\"stable_samples\":{_q5StableSamples}}}");
                _phaseStep=2;StartCurrentPhase();
            }
            else if(_phaseStep==2&&_q5ValidSamples>=500)
            {
                ConfirmCurrentPhase("phase_confirmed_by_app",$"{{\"valid_samples\":{_q5ValidSamples}}}");
                CompleteSequence($"{{\"valid_samples\":{_q5ValidSamples}}}");_phaseStep=3;StartCurrentPhase();
            }
        }

        void CaptureQrMatrixSample()
        {
            var valid=TryCaptureQr(out var qr,out var status);if(valid)_phaseValidSamples++;
            LogQrSample(qr,status);
        }

        bool TryCaptureQr(out QrMarkerObservation qr,out string status)
        {
            var tracker=RobotMarkerTrackerRegistry.Current;qr=default;
            var requiredPayload=_q5PayloadLocked&&_q5Payload!="<binary>"?_q5Payload:null;
            var valid=tracker!=null&&tracker.TryGetQrSnapshot(requiredPayload,out qr)&&qr.Valid;
            status=tracker?.StatusReason??"QR-трекер недоступен";
            if(valid&&!_q5PayloadLocked)
            {
                _q5Payload=qr.Payload;_q5PayloadLocked=true;
                _logger.Log(_test.ToString(),"qr_acquired",CurrentPhase,"",JsonUtility.ToJson(qr));
            }
            return valid;
        }

        void LogQrSample(QrMarkerObservation qr,string status)
        {
            var room=RoomReferenceRegistry.Current;
            _logger.Log(_test.ToString(),"tracking_sample",CurrentPhase,"",JsonUtility.ToJson(new QrTrackingSample
            {
                tracking=_last,qr=qr,tracker_status=status,room_ready=room?.IsReady==true
            }));
        }

        void AdvanceQrMatrixPhase()
        {
            if(_phaseValidSamples<Q6RequiredValidSamplesPerCell)
            {
                _logger.Log(_test.ToString(),"phase_confirmation_rejected",CurrentPhase,"",$"{{\"valid_samples\":{_phaseValidSamples}}}");return;
            }
            AdvanceGuidedPhase();_phaseValidSamples=0;
        }

        void CaptureMarkerRigSample()
        {
            var tracker=RobotMarkerTrackerRegistry.Current;
            RobotMarkerSnapshot snapshot=null;
            var valid=tracker!=null&&tracker.TryGetSnapshot(out snapshot);
            if(valid)_phaseValidSamples++;
            var geometry=valid?new RobotGeometryEstimator().Estimate(snapshot.Positions,snapshot.BaseFrame):default;
            _logger.Log(_test.ToString(),"tracking_sample",CurrentPhase,"",JsonUtility.ToJson(new MarkerRigTrackingSample
            {
                tracking=_last,valid=valid,tracker_status=tracker?.StatusReason??"трекер меток недоступен",geometry=geometry,
                base_back=Marker(snapshot,RobotMarkerId.BaseBack),shoulder_l=Marker(snapshot,RobotMarkerId.ShoulderL),shoulder_r=Marker(snapshot,RobotMarkerId.ShoulderR),
                elbow_l=Marker(snapshot,RobotMarkerId.ElbowL),elbow_r=Marker(snapshot,RobotMarkerId.ElbowR),tcp_cal=Marker(snapshot,RobotMarkerId.TcpCal)
            }));
        }

        static Vec3 Marker(RobotMarkerSnapshot snapshot,RobotMarkerId id)=>snapshot!=null&&snapshot.Positions.TryGetValue(id,out var value)?value:Vec3.Zero;

        void AdvanceMarkerRigPhase()
        {
            if(_phaseValidSamples<Q7RequiredValidSamplesPerScan)
            {
                _logger.Log(_test.ToString(),"phase_confirmation_rejected",CurrentPhase,"",$"{{\"valid_samples\":{_phaseValidSamples}}}");return;
            }
            AdvanceGuidedPhase();_phaseValidSamples=0;
        }

        static double QrPositionDelta(QrMarkerObservation a,QrMarkerObservation b)
        {
            var dx=a.PositionRoom.X-b.PositionRoom.X;var dy=a.PositionRoom.Y-b.PositionRoom.Y;var dz=a.PositionRoom.Z-b.PositionRoom.Z;
            return Math.Sqrt(dx*dx+dy*dy+dz*dz);
        }

        static double QrAngleDegrees(QrMarkerObservation a,QrMarkerObservation b)
        {
            var dot=Math.Abs(a.RotationX*b.RotationX+a.RotationY*b.RotationY+a.RotationZ*b.RotationZ+a.RotationW*b.RotationW);
            dot=Math.Max(-1.0,Math.Min(1.0,dot));return Math.Acos(dot)*2.0*180.0/Math.PI;
        }

        void AdvanceGuidedPhase()
        {
            ConfirmCurrentPhase();
            if(_phaseStep>=PhaseCount(_test)-1){CompleteSequence($"{{\"step\":{_phaseStep}}}");return;}
            _phaseStep++;StartCurrentPhase();
        }

        void ConfirmCurrentPhase(string eventName="phase_confirmed_by_user",string payload=null)
            =>_logger.Log(_test.ToString(),eventName,CurrentPhase,"",payload??JsonUtility.ToJson(_last));

        void StartCurrentPhase()=>_logger.Log(_test.ToString(),"phase_start",CurrentPhase,"",$"{{\"step\":{_phaseStep}}}");

        void CompleteSequence(string payload)
        {
            if(_sequenceComplete)return;_sequenceComplete=true;
            _logger.Log(_test.ToString(),"sequence_complete",CurrentPhase,"",payload);
        }

        string CurrentPhase
        {
            get
            {
                if(_test==QuestTestId.Q2_Grasp)return $"repeat_{_phaseStep/GraspTokens.Length+1}_{GraspTokens[_phaseStep%GraspTokens.Length]}";
                if(_test==QuestTestId.Q5_FixedQr)return $"step_{_phaseStep+1}_of_4";
                if(_test==QuestTestId.Q6_QrMatrix)
                {
                    Q6Cell(_phaseStep,out var size,out var distance,out var angle);
                    return $"cell_{_phaseStep+1}_of_48_{size}mm_{distance.ToString("F1",CultureInfo.InvariantCulture)}m_{angle}deg";
                }
                return $"step_{_phaseStep+1}_of_{PhaseCount(_test)}";
            }
        }

        public void StartRun(QuestTestId test)
        {
            StopRun();_test=test;_samples=0;_phaseStep=0;_phaseValidSamples=0;_sequenceComplete=false;
            _triggerPressedAt=-1f;
            _q5ValidSamples=0;_q5StableSamples=0;_q5Payload=null;_q5PayloadLocked=false;_q5PreviousValid=false;
            _logger=new QuestJsonlLogger();_running=true;
            RobotMarkerTrackerRegistry.Current?.SetQrTrackingEnabled(UsesQrTracking(_test));
            _logger.Log(_test.ToString(),"run_start",CurrentPhase,"",JsonUtility.ToJson(new RunMetadata{phase_count=PhaseCount(_test)}));StartCurrentPhase();
        }

        public void StopRun()
        {
            if(!_running)return;
            _logger.Log(_test.ToString(),"run_stop",CurrentPhase,"",$"{{\"sample_count\":{_samples},\"sequence_complete\":{_sequenceComplete.ToString().ToLowerInvariant()}}}");
            if(UsesQrTracking(_test))RobotMarkerTrackerRegistry.Current?.SetQrTrackingEnabled(false);
            _logger.Dispose();_logger=null;_running=false;
        }

        static bool UsesQrTracking(QuestTestId test)=>test==QuestTestId.Q5_FixedQr||test==QuestTestId.Q6_QrMatrix||test==QuestTestId.Q7_MarkerRig||test==QuestTestId.Q13_QrAbsoluteJointReference||test==QuestTestId.Q14_QrEncoderCrossCheck;
        void OnDestroy(){StopRun();}

        static int PhaseCount(QuestTestId test)
        {
            switch(test)
            {
                case QuestTestId.Q0_Environment:return Q0Phases.Length;
                case QuestTestId.Q1_Multimodal:return Q1Phases.Length;
                case QuestTestId.Q2_Grasp:return GraspTokens.Length*5;
                case QuestTestId.Q3_WristVsPalm:return Q3Phases.Length;
                case QuestTestId.Q4_RoomStability:return Q4Phases.Length;
                case QuestTestId.Q5_FixedQr:return 4;
                case QuestTestId.Q6_QrMatrix:return 48;
                case QuestTestId.Q7_MarkerRig:return 20;
                case QuestTestId.Q8_UserShoulderFit:return 28;
                case QuestTestId.Q9_Drift:return 50;
                case QuestTestId.Q10_TrackingPauseLoss:return Q10Phases.Length;
                case QuestTestId.Q11_UdpSimulator:return Q11Phases.Length;
                case QuestTestId.Q12_FullStartupDryRun:return Q12Phases.Length;
                case QuestTestId.Q13_QrAbsoluteJointReference:return 150;
                case QuestTestId.Q14_QrEncoderCrossCheck:return 20;
                default:return 1;
            }
        }

        string InstructionsForCurrentPhase()
        {
            switch(_test)
            {
                case QuestTestId.Q0_Environment:return Q0Phases[Math.Min(_phaseStep,Q0Phases.Length-1)];
                case QuestTestId.Q1_Multimodal:return Q1Phases[Math.Min(_phaseStep,Q1Phases.Length-1)];
                case QuestTestId.Q2_Grasp:return $"Повтор {_phaseStep/GraspTokens.Length+1}/5. Правая рука: {GraspLabels[_phaseStep%GraspLabels.Length]}. Держите позу 2 секунды и нажмите X.";
                case QuestTestId.Q3_WristVsPalm:return Q3Phases[Math.Min(_phaseStep,Q3Phases.Length-1)];
                case QuestTestId.Q4_RoomStability:return Q4Phases[Math.Min(_phaseStep,Q4Phases.Length-1)];
                case QuestTestId.Q5_FixedQr:return Q5Instruction();
                case QuestTestId.Q6_QrMatrix:return Q6Instruction();
                case QuestTestId.Q7_MarkerRig:return $"Скан {_phaseStep+1}/20. Уберите комплект из поля зрения на 2 секунды, затем покажите все 6 жёстко закреплённых меток. Когда счётчик заполнится, нажмите X.";
                case QuestTestId.Q8_UserShoulderFit:return Q8Instruction(_phaseStep);
                case QuestTestId.Q9_Drift:return $"Цикл {_phaseStep+1}/50: центр → {DriftDirection(_phaseStep)} → центр. Двигайте прямой рукой без шага корпусом, затем нажмите X.";
                case QuestTestId.Q10_TrackingPauseLoss:return Q10Phases[Math.Min(_phaseStep,Q10Phases.Length-1)];
                case QuestTestId.Q11_UdpSimulator:return Q11Phases[Math.Min(_phaseStep,Q11Phases.Length-1)];
                case QuestTestId.Q12_FullStartupDryRun:return Q12Phases[Math.Min(_phaseStep,Q12Phases.Length-1)];
                case QuestTestId.Q13_QrAbsoluteJointReference:return Q13Instruction(_phaseStep);
                case QuestTestId.Q14_QrEncoderCrossCheck:return $"Цикл {_phaseStep+1}/20. МОТОРЫ ОТКЛЮЧЕНЫ: сканируйте абсолютные углы QR, задайте смещения энкодеров, выполните медленную проверочную позу и повторный QR-скан. После записи нажмите X.";
                default:return "Следуйте инструкции и нажмите X после выполнения.";
            }
        }

        string Q5Instruction()
        {
            if(_phaseStep==0)return "Жёстко закрепите один QR примерно в 1,0 м прямо перед собой. Не держите его рукой. Нажмите X.";
            if(_phaseStep==1)return "Не трогайте QR и держите его в поле зрения. Приложение автоматически ждёт устойчивое распознавание.";
            if(_phaseStep==2)return "Не трогайте QR. Держите его видимым до автоматической записи 500 валидных поз.";
            return "Запись 500 поз завершена. Удерживайте курок 2 секунды, чтобы сохранить запуск.";
        }

        string Q6Instruction()
        {
            Q6Cell(_phaseStep,out var size,out var distance,out var angle);
            return $"QR_TEST {size} мм; расстояние {distance.ToString("F1",CultureInfo.InvariantCulture)} м; угол {angle}°. Закрепите по линейке/шаблону, держите видимым до 20 кадров и нажмите X.";
        }

        static void Q6Cell(int index,out int size,out float distance,out int angle)
        {
            var sizes=new[]{30,40,50,60};var distances=new[]{.5f,1f,1.5f,2f};var angles=new[]{0,30,45};
            angle=angles[index%angles.Length];index/=angles.Length;distance=distances[index%distances.Length];index/=distances.Length;size=sizes[index%sizes.Length];
        }

        static string Q8Instruction(int index)
        {
            if(index<10)return $"Нормальная серия {index+1}/10: Y — старт, выполните горизонтальную, вертикальную и диагональную дуги прямой рукой; Y — завершить; затем X.";
            if(index<15)return $"Согнутый локоть {index-9}/5: Y — старт, выполните дуги с намеренно согнутым локтем; Y — завершить; затем X.";
            if(index<20)return $"Недостаточное покрытие {index-14}/5: Y — старт, выполните только маленькую часть одной дуги; Y — завершить; затем X.";
            if(index<25)return $"Только поворот головы {index-19}/5: Y — старт, держите руку неподвижно и поворачивайте только голову; Y — завершить; затем X.";
            return $"Шаг корпусом {index-24}/3: Y — старт, во время дуг намеренно сделайте шаг; Y — завершить; затем X.";
        }

        static string DriftDirection(int index)=>index%3==0?"вправо":index%3==1?"влево":"вверх";

        static string Q13Instruction(int index)
        {
            var axes=new[]{"ОСНОВАНИЕ","ПЛЕЧО","ЛОКОТЬ"};var angles=new[]{"0°","+45°","−45°","+90°","−90°"};
            var repeat=index%10+1;var pose=index/10;var angle=angles[pose%angles.Length];var axis=axes[(pose/angles.Length)%axes.Length];
            return $"СТЕНД С ЖЁСТКИМИ МЕТКАМИ. {axis}, угол {angle}, повтор {repeat}/10. Моторы отключены; установите известный угол, дождитесь QR и нажмите X.";
        }

        static string TestTitle(QuestTestId test)
        {
            switch(test)
            {
                case QuestTestId.Q0_Environment:return "Q0 СРЕДА И ИНТЕРФЕЙС";
                case QuestTestId.Q1_Multimodal:return "Q1 РУКА + КОНТРОЛЛЕР";
                case QuestTestId.Q2_Grasp:return "Q2 СЖАТИЕ КИСТИ";
                case QuestTestId.Q3_WristVsPalm:return "Q3 ЗАПЯСТЬЕ И ЛАДОНЬ";
                case QuestTestId.Q4_RoomStability:return "Q4 СТАБИЛЬНОСТЬ КОМНАТЫ";
                case QuestTestId.Q5_FixedQr:return "Q5 НЕПОДВИЖНЫЙ QR";
                case QuestTestId.Q6_QrMatrix:return "Q6 МАТРИЦА QR";
                case QuestTestId.Q7_MarkerRig:return "Q7 МЕТКИ РОБОТА";
                case QuestTestId.Q8_UserShoulderFit:return "Q8 КАЛИБРОВКА ПЛЕЧА";
                case QuestTestId.Q9_Drift:return "Q9 ДРЕЙФ ЦЕЛИ";
                case QuestTestId.Q10_TrackingPauseLoss:return "Q10 ПОТЕРЯ СЛЕЖЕНИЯ";
                case QuestTestId.Q11_UdpSimulator:return "Q11 СЕТЕВЫЕ ОТКАЗЫ";
                case QuestTestId.Q12_FullStartupDryRun:return "Q12 ПОЛНЫЙ ЗАПУСК";
                case QuestTestId.Q13_QrAbsoluteJointReference:return "Q13 УГЛЫ ПО QR";
                case QuestTestId.Q14_QrEncoderCrossCheck:return "Q14 QR И ЭНКОДЕРЫ";
                default:return test.ToString();
            }
        }

        static string TestPurpose(QuestTestId test)
        {
            switch(test)
            {
                case QuestTestId.Q0_Environment:return "проверить MR, интерфейс и стабильность виртуального слоя";
                case QuestTestId.Q1_Multimodal:return "проверить одновременное слежение правой руки и левого Touch Plus";
                case QuestTestId.Q2_Grasp:return "измерить значение сжатия на пяти полных повторах";
                case QuestTestId.Q3_WristVsPalm:return "сравнить устойчивость поз запястья и ладони";
                case QuestTestId.Q4_RoomStability:return "проверить систему координат комнаты после движения, меню и переноса центра";
                case QuestTestId.Q5_FixedQr:return "измерить стабильность позы одного неподвижного QR";
                case QuestTestId.Q6_QrMatrix:return "проверить QR разных размеров, расстояний и углов";
                case QuestTestId.Q7_MarkerRig:return "измерить геометрию робота по 20 независимым сканам";
                case QuestTestId.Q8_UserShoulderFit:return "проверить нормальные и ошибочные серии калибровки пользователя";
                case QuestTestId.Q9_Drift:return "проверить отсутствие накопления ошибки за 50 циклов";
                case QuestTestId.Q10_TrackingPauseLoss:return "проверить безопасную остановку и явное повторное включение";
                case QuestTestId.Q11_UdpSimulator:return "проверить восемь сетевых режимов и отказов";
                case QuestTestId.Q12_FullStartupDryRun:return "пройти полный путь от запуска до безопасного восстановления";
                case QuestTestId.Q13_QrAbsoluteJointReference:return "оценить абсолютные углы трёх шарниров по жёстким QR";
                case QuestTestId.Q14_QrEncoderCrossCheck:return "сверить стартовую QR-привязку с энкодерами";
                default:return "инженерная проверка";
            }
        }

        [Serializable] sealed class RunMetadata
        {
            public string unity_version=Application.unityVersion;public string platform=Application.platform.ToString();public string device_model=SystemInfo.deviceModel;public int phase_count;
        }
        [Serializable] sealed class RoomTrackingSample{public TrackingFrame tracking;public bool room_ready;public string room_status;public Vec3 floor_origin;}
        [Serializable] sealed class QrTrackingSample{public TrackingFrame tracking;public QrMarkerObservation qr;public string tracker_status;public bool room_ready;}
        [Serializable] sealed class MarkerRigTrackingSample
        {
            public TrackingFrame tracking;public bool valid;public string tracker_status;public RobotGeometry geometry;
            public Vec3 base_back,shoulder_l,shoulder_r,elbow_l,elbow_r,tcp_cal;
        }

        void OnGUI()
        {
#if UNITY_EDITOR
            GUI.Box(new Rect(20,20,920,285),"PHANTOM — ПРОВЕРКА QUEST");
            GUI.Label(new Rect(35,50,890,45),Summary);GUI.Label(new Rect(35,95,890,90),Instructions);
            GUI.Label(new Rect(35,185,890,42),$"правая рука={_last.RightHand.Valid}  левый контроллер={_last.LeftController.Valid}  оба={_last.BothValid}  фокус={_last.AppFocused}");
            GUI.Label(new Rect(35,225,890,42),$"мультимодальность={_last.MultimodalConfigured}  режим={_last.InteractionMode}  сжатие готово={_last.RightHand.Grasp.Ready}  сжатие={_last.RightHand.Grasp.Value01:F3}");
            if(GUI.Button(new Rect(35,265,100,30),"СТАРТ"))StartRun(_test);if(GUI.Button(new Rect(145,265,120,30),"СТОП/СОХР."))StopRun();
            if(!_running&&GUI.Button(new Rect(275,265,100,30),"НАЗАД"))_test=(QuestTestId)Math.Max(0,(int)_test-1);
            if(!_running&&GUI.Button(new Rect(385,265,100,30),"ДАЛЕЕ"))_test=(QuestTestId)Math.Min(14,(int)_test+1);
#endif
        }
    }
}
