using System.Linq;
using NUnit.Framework;
using Phantom.Diagnostics;

namespace Phantom.Tests
{
    public sealed class QuestQualificationTests
    {
        static BodyProviderProbe ConfiguredProbe()=>new BodyProviderProbe
        {
            ApiPresent=true,ComponentPresent=true,UpperBodyConfigured=true,RightShoulderInJointSet=true
        };

        [Test]
        public void InactiveHmdWithoutLiveSamplesIsNotACompatibilityFailure()
        {
            var probe=ConfiguredProbe();
            probe.XrSessionActive=false;probe.XrFocusActive=false;probe.LiveObservationAvailable=false;
            var result=BodyProviderClassifier.Classify(probe);
            Assert.That(result.State,Is.EqualTo(BodyProviderOperationalState.ConfiguredLifecycleInactive));
            Assert.That(result.SoftwareCompatible,Is.True);
        }

        [Test]
        public void ExplicitOvrBodyMultimodalDisableIsACompatibilityFailure()
        {
            var probe=ConfiguredProbe();probe.ExplicitMultimodalConflict=true;
            var result=BodyProviderClassifier.Classify(probe);
            Assert.That(result.State,Is.EqualTo(BodyProviderOperationalState.ExplicitlyDisabledOrIncompatible));
            Assert.That(result.SoftwareCompatible,Is.False);
            Assert.That(BodyProviderClassifier.IsExplicitOvrBodyMultimodalConflict("OVRBody/com.meta.xr.sdk.core","205.0.0",true),Is.True);
        }

        [Test]
        public void ProviderApiAbsenceAndActiveInitializationFailureAreDistinct()
        {
            Assert.That(BodyProviderClassifier.Classify(default).State,Is.EqualTo(BodyProviderOperationalState.ApiAbsent));
            var probe=ConfiguredProbe();probe.XrSessionActive=true;probe.XrFocusActive=true;probe.InitializationAttempted=true;
            Assert.That(BodyProviderClassifier.Classify(probe).State,Is.EqualTo(BodyProviderOperationalState.InitializationFailed));
        }

        [Test]
        public void DiagnosticSyntheticQualificationCoversAllRequiredCases()
        {
            var results=QuestSyntheticQualification.Run();
            Assert.That(results.Length,Is.GreaterThanOrEqualTo(12));
            Assert.That(results.All(result=>result.passed),Is.True,string.Join(",",results.Where(result=>!result.passed).Select(result=>result.test_id)));
        }
    }
}
