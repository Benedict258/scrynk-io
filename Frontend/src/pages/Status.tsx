import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Clock, Download, FileText } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const Status = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleDownload = async (format: "csv" | "txt") => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/download/?format=${format}`);
      if (!response.ok) throw new Error("Download failed");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", format === "csv" ? "emails.csv" : "emails.txt");
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Download error:", error);
      toast({
        title: "Download Failed",
        description: "Could not download emails. Try again.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="min-h-screen bg-background py-16">
      <div className="container mx-auto px-4 max-w-4xl">
        <div className="mb-8">
          <Button
            variant="ghost"
            onClick={() => navigate('/')}
            className="font-kode mb-4 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Home
          </Button>
          <h1 className="font-bungee text-4xl text-primary mb-2">
            Status Dashboard
          </h1>
          <p className="font-kode text-muted-foreground">
            Track your extraction runs and manage results
          </p>
        </div>

        <div className="space-y-6">
          {/* Status Card */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="font-rampart text-lg flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Extraction Results
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="font-kode text-sm text-muted-foreground mb-4">
                Download the latest extracted emails below:
              </p>
              <div className="flex gap-4">
                <Button onClick={() => handleDownload("csv")} className="flex-1">
                  <Download className="w-4 h-4 mr-2" /> Download CSV
                </Button>
                <Button onClick={() => handleDownload("txt")} className="flex-1">
                  <Download className="w-4 h-4 mr-2" /> Download TXT
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex gap-4 justify-center">
            <Button
              onClick={() => navigate('/extract')}
              className="font-rampart bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              Start New Extraction
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/')}
              className="font-rampart"
            >
              Back to Home
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Status;
