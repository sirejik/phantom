using Phantom.Mapping;

namespace Phantom.UI
{
    public static class StartupWizardModel
    {
        public static string Instruction(PhantomState state,PhantomFault fault=PhantomFault.None)
        {
            switch(state)
            {
                case PhantomState.Boot:return "Проверьте OpenXR, LOCAL_FLOOR, Spatial Data и QR Trackables.";
                case PhantomState.Discovery:return "Идёт поиск PHANTOM EV3 по имени робота в локальной сети.";
                case PhantomState.ConnectedUnreferenced:return "Покажите все QR-маркеры для привязки энкодеров.";
                case PhantomState.RobotCalibration:return "Покажите неподвижно метки основания, плеч, локтей и рабочего инструмента не менее одной секунды.";
                case PhantomState.UserCalibration:return "Встаньте в рабочей зоне. Y — начать; сделайте три большие дуги прямой рукой; Y — завершить.";
                case PhantomState.Commissioning:return "Робот выполняет ввод в эксплуатацию. Дождитесь завершения и не нажимайте кнопку захвата.";
                case PhantomState.Ready:case PhantomState.Hold:return "Проверьте виртуальную цель, отпустите и затем заново нажмите левую кнопку захвата.";
                case PhantomState.Tracking:return "Управление включено. Отпустите левую кнопку захвата для немедленной остановки.";
                case PhantomState.SafeHold:return "Отпустите левую кнопку захвата, устраните причину остановки и только затем нажмите её снова.";
                // STOPPED is latched: releasing the trigger is necessary but never
                // sufficient. A latched fault is carried alongside the state rather
                // than as a state of its own, so it changes the wording, not the case.
                case PhantomState.Stopped:
                    return fault==PhantomFault.None
                        ?"ОСТАНОВЛЕНО. Отпустите левую кнопку захвата, устраните причину и подтвердите снятие блокировки на роботе."
                        :"ОСТАНОВЛЕНО ПО ОШИБКЕ. Отпустите левую кнопку захвата, устраните ошибку, подтвердите её и только затем снимите блокировку.";
                default:return "";
            }
        }
    }
}
